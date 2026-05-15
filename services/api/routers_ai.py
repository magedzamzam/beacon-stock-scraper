"""AI provider settings + on-demand stock/portfolio analysis."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db import (
    AIProviderSetting, AIPromptTemplate, Exchange, PortfolioPosition, Stock,
    StockAnalystConsensus, StockFinRatios, StockFinStatement, StockMktTechnicals,
    StockNews, StockQuote, User,
)
from .auth import get_current_user, get_db
from .routers_portfolio import _build_position_out
from .routers_stocks import _row_to_summary
from .routers_watchlists import _stock_summary
from .schemas import (
    AIAnalysisResponse, AIAnalysisResult, AIAnalysisRequest, AIProviderSettingOut,
    AIProviderSettingUpsert, AIPromptTemplateOut,
)

router = APIRouter(prefix="/ai", tags=["ai"])


PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "ChatGPT",
        "default_model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "system_header": None,
    },
    "gemini": {
        "label": "Gemini",
        "default_model": "gemini-2.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "chat_path": "/models/{model}:generateContent",
        "auth_header": "x-goog-api-key",
        "auth_prefix": None,
        "system_header": None,
    },
    "anthropic": {
        "label": "Claude",
        "default_model": "claude-sonnet-4-latest",
        "base_url": "https://api.anthropic.com/v1",
        "chat_path": "/messages",
        "auth_header": "x-api-key",
        "auth_prefix": None,
        "system_header": "anthropic-version",
        "system_header_value": "2023-06-01",
    },
    "xai": {
        "label": "Grok",
        "default_model": "grok-4-fast",
        "base_url": "https://api.x.ai/v1",
        "chat_path": "/responses",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "system_header": None,
    },
}

PROMPTS: dict[str, dict[str, Any]] = {
    "stock_brief": {
        "key": "stock_brief",
        "label": "Stock analysis",
        "scope": "stock",
        "description": "Compact single-stock analysis with an independent verdict and reasons.",
        "system_prompt": (
            "You are an independent equity analyst. Form your own view of the stock "
            "using public knowledge of the company, sector, valuation norms, and macro "
            "context. Do NOT assume any third-party verdicts, scores, technical "
            "indicators, or analyst targets — none are provided. Return only valid "
            "JSON. Keep every field short. Use the fewest possible tokens. No markdown, "
            "no preamble, no commentary."
        ),
        "max_output_tokens": 600,
    },
    "portfolio_brief": {
        "key": "portfolio_brief",
        "label": "Portfolio analysis",
        "scope": "portfolio",
        "description": (
            "Compact portfolio review with independent per-position actions."
        ),
        "system_prompt": (
            "You are an independent portfolio strategist. Evaluate each position on "
            "its own merits using public knowledge of the company, sector, and macro "
            "context. Identify concentration risk and diversification gaps. Do NOT "
            "assume any third-party verdicts or scores — none are provided. Return "
            "only valid JSON. Keep every field short. Use the fewest possible tokens. "
            "No markdown, no preamble, no commentary."
        ),
        "max_output_tokens": 800,
    },
}


class AIProviderSettingUpsertLocal(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None


class AIAnalysisPositionOut(BaseModel):
    position_id: int
    ticker: str
    exchange_code: str
    company_name: str
    quantity: float
    avg_entry_price: float
    current_price: Optional[float] = None
    unrealized_pl_pct: Optional[float] = None
    position_verdict: Optional[str] = None
    position_confidence: Optional[float] = None


class AIAnalysisContextOut(BaseModel):
    scope: str
    prompt_key: str
    stock: Optional[dict[str, Any]] = None
    portfolio: Optional[dict[str, Any]] = None
    positions: list[AIAnalysisPositionOut] = []


class AIAnalysisRequestBody(AIAnalysisRequest):
    pass


class AIAnalysisResponseOut(AIAnalysisResponse):
    pass


class AIProviderSettingSeed(BaseModel):
    provider_key: str
    provider_name: str
    enabled: bool
    api_key_present: bool
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_error: Optional[str] = None
    updated_at: Optional[datetime] = None


def _provider_defaults(provider_key: str) -> dict[str, Any]:
    meta = PROVIDERS[provider_key]
    return {
        "provider_key": provider_key,
        "provider_name": meta["label"],
        "enabled": False,
        "api_key": None,
        "model_name": meta["default_model"],
        "base_url": meta["base_url"],
        "last_tested_at": None,
        "last_test_status": None,
        "last_test_error": None,
        "updated_at": None,
    }


def _provider_row_out(row: AIProviderSetting | None, provider_key: str) -> AIProviderSettingSeed:
    meta = PROVIDERS[provider_key]
    if row is None:
        defaults = _provider_defaults(provider_key)
        return AIProviderSettingSeed(
            provider_key=provider_key,
            provider_name=meta["label"],
            enabled=False,
            api_key_present=False,
            model_name=defaults["model_name"],
            base_url=defaults["base_url"],
            last_tested_at=None,
            last_test_status=None,
            last_test_error=None,
            updated_at=None,
        )
    return AIProviderSettingSeed(
        provider_key=provider_key,
        provider_name=meta["label"],
        enabled=bool(row.enabled),
        api_key_present=bool(row.api_key),
        model_name=row.model_name or meta["default_model"],
        base_url=row.base_url or meta["base_url"],
        last_tested_at=row.last_tested_at,
        last_test_status=row.last_test_status,
        last_test_error=row.last_test_error,
        updated_at=row.updated_at,
    )


def _upsert_provider(db: Session, user: User, provider_key: str, body: AIProviderSettingUpsertLocal) -> AIProviderSetting:
    meta = PROVIDERS[provider_key]
    existing = db.execute(
        select(AIProviderSetting).where(
            AIProviderSetting.user_id == user.id,
            AIProviderSetting.provider_key == provider_key,
        )
    ).scalar_one_or_none()
    api_key = body.api_key
    if api_key in (None, "") and existing is not None:
        api_key = existing.api_key
    model_name = body.model_name or (existing.model_name if existing and existing.model_name else meta["default_model"])
    base_url = body.base_url or (existing.base_url if existing and existing.base_url else meta["base_url"])
    stmt = pg_insert(AIProviderSetting).values(
        user_id=user.id,
        provider_key=provider_key,
        provider_name=meta["label"],
        enabled=body.enabled,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        updated_at=datetime.utcnow(),
        updated_by=user.id,
    ).on_conflict_do_update(
        index_elements=["user_id", "provider_key"],
        set_={
            "provider_name": meta["label"],
            "enabled": body.enabled,
            "api_key": api_key,
            "model_name": model_name,
            "base_url": base_url,
            "updated_at": datetime.utcnow(),
            "updated_by": user.id,
        },
    )
    db.execute(stmt)
    db.commit()
    row = db.execute(
        select(AIProviderSetting).where(
            AIProviderSetting.user_id == user.id,
            AIProviderSetting.provider_key == provider_key,
        )
    ).scalar_one()
    return row


def _sanitize_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _extract_text(payload: dict[str, Any], provider_key: str) -> str:
    if provider_key in {"openai", "xai"}:
        choices = payload.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            return msg.get("content") or ""
        return ""
    if provider_key == "anthropic":
        chunks = payload.get("content") or []
        texts = []
        for chunk in chunks:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                texts.append(chunk.get("text") or "")
        return "".join(texts)
    if provider_key == "gemini":
        candidates = payload.get("candidates") or []
        if candidates:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
            return "".join(texts)
    return payload.get("text") or payload.get("output_text") or ""


async def _call_provider(provider_key: str, cfg: AIProviderSetting, prompt: str, max_tokens: int) -> dict[str, Any]:
    meta = PROVIDERS[provider_key]
    api_key = cfg.api_key or ""
    model = cfg.model_name or meta["default_model"]
    base_url = (cfg.base_url or meta["base_url"]).rstrip("/")
    timeout = httpx.Timeout(60.0, connect=15.0)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "beacon-ai/1.0",
    }
    if meta["auth_header"] == "Authorization":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers[meta["auth_header"]] = api_key
    if meta.get("system_header"):
        headers[meta["system_header"]] = meta.get("system_header_value", "")

    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider_key in {"openai", "xai"}:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Return only JSON. Keep it short."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
            }
            url = f"{base_url}{meta['chat_path']}"
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        if provider_key == "anthropic":
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "system": "Return only JSON. Keep it short.",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
            url = f"{base_url}{meta['chat_path']}"
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        if provider_key == "gemini":
            # Gemini 2.5/3 Flash have "thinking" enabled by default, which
            # silently eats from maxOutputTokens — leaving the visible JSON
            # response truncated. We disable thinking for 2.5 Flash (the
            # supported model that allows it) by setting thinkingBudget=0.
            # For Gemini 3 models, thinking can't be fully disabled — only
            # set to "low" — so we set thinkingLevel as a best effort and
            # rely on the bumped max_tokens to cover both budgets.
            generation_config: dict[str, Any] = {
                "temperature": 0,
                "maxOutputTokens": max_tokens,
            }
            model_lower = (model or "").lower()
            if "2.5" in model_lower:
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            elif model_lower.startswith("gemini-3") or "3-flash" in model_lower or "3.1" in model_lower:
                # gemini-3 family — minimum supported is "low"
                generation_config["thinkingConfig"] = {"thinkingLevel": "low"}
            payload = {
                "systemInstruction": {
                    "parts": [{"text": "Return only JSON. Keep it short."}],
                },
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            }
            url = f"{base_url}{meta['chat_path'].format(model=model.lstrip('/'))}"
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    raise HTTPException(500, f"Unsupported provider '{provider_key}'")


def _build_stock_context(db: Session, exchange: str, ticker: str) -> dict[str, Any]:
    row = db.execute(
        select(
            Stock.id, Stock.ticker, Stock.company_name, Stock.sector, Stock.industry,
            Stock.country, Stock.currency, Exchange.code.label("exchange_code"),
            StockQuote.current_price, StockQuote.change_pct, StockQuote.market_cap,
            StockQuote.pe_ratio, StockQuote.dividend_yield_pct, StockQuote.rsi_14,
            StockQuote.composite_score, StockQuote.verdict, StockQuote.last_updated,
            StockQuote.prev_close, StockQuote.change_abs, StockQuote.price_source,
            StockQuote.price_fetched_at, StockQuote.week_52_high, StockQuote.week_52_low,
            StockQuote.analyst_target, StockQuote.analyst_upside_pct,
        )
        .join(Exchange, Stock.exchange_id == Exchange.id)
        .outerjoin(StockQuote, StockQuote.stock_id == Stock.id)
        .where(
            Exchange.code.ilike(exchange),
            Stock.ticker.ilike(ticker),
        )
    ).first()
    if not row:
        raise HTTPException(404, "Stock not found")

    analyst = db.execute(
        select(StockAnalystConsensus)
        .where(StockAnalystConsensus.stock_id == row.id)
        .order_by(StockAnalystConsensus.consensus_date.desc())
        .limit(1)
    ).scalars().first()
    fin_ratios = db.execute(
        select(StockFinRatios)
        .where(StockFinRatios.stock_id == row.id)
        .order_by(StockFinRatios.period_end.desc(), StockFinRatios.id.desc())
        .limit(1)
    ).scalars().first()
    fin_stmt = db.execute(
        select(StockFinStatement)
        .where(StockFinStatement.stock_id == row.id, StockFinStatement.is_estimate.is_(False))
        .order_by(StockFinStatement.period_end.desc(), StockFinStatement.id.desc())
        .limit(1)
    ).scalars().first()
    tech = db.execute(
        select(StockMktTechnicals)
        .where(StockMktTechnicals.stock_id == row.id)
        .order_by(StockMktTechnicals.trading_date.desc())
        .limit(1)
    ).scalars().first()
    news = db.execute(
        select(StockNews)
        .where(StockNews.stock_id == row.id)
        .order_by(StockNews.news_date.desc().nullslast(), StockNews.id.desc())
        .limit(5)
    ).scalars().all()

    summary = _row_to_summary(row)
    stock = summary.model_dump()
    stock.update({
        "isin": None,
        "founded_year": None,
        "employees": None,
        "website": None,
        "beta": float(tech.beta) if tech and tech.beta is not None else None,
        "forward_pe": float(fin_ratios.pe_forward) if fin_ratios and fin_ratios.pe_forward is not None else None,
        "week_52_high": float(row.week_52_high) if row.week_52_high is not None else None,
        "week_52_low": float(row.week_52_low) if row.week_52_low is not None else None,
        "enterprise_value": float(fin_ratios.snapshot_market_cap) if fin_ratios and fin_ratios.snapshot_market_cap is not None else None,
        "revenue_ttm": float(fin_stmt.revenue) if fin_stmt and fin_stmt.revenue is not None else None,
        "sma_50": float(tech.sma_50) if tech and tech.sma_50 is not None else None,
        "sma_200": float(tech.sma_200) if tech and tech.sma_200 is not None else None,
        "analyst_target": float(row.analyst_target) if row.analyst_target is not None else None,
        "analyst_upside_pct": float(row.analyst_upside_pct) if row.analyst_upside_pct is not None else None,
        "analyst_count": analyst.analyst_count if analyst else None,
        "analyst_rating": analyst.rating if analyst else None,
        "current_price": float(row.current_price) if row.current_price is not None else None,
        "prev_close": float(row.prev_close) if row.prev_close is not None else None,
        "change_abs": float(row.change_abs) if row.change_abs is not None else None,
        "change_pct": float(row.change_pct) if row.change_pct is not None else None,
        "price_source": row.price_source,
        "price_fetched_at": row.price_fetched_at,
        "news": [
            {
                "headline": n.headline,
                "summary": n.summary,
                "sentiment_label": n.sentiment_label,
                "sentiment_score": float(n.sentiment_score) if n.sentiment_score is not None else None,
            }
            for n in news
        ],
    })
    return stock


def _build_portfolio_context(db: Session, user: User, account_id: Optional[int]) -> dict[str, Any]:
    query = select(PortfolioPosition).where(
        PortfolioPosition.user_id == user.id,
        PortfolioPosition.is_open.is_(True),
    )
    if account_id is not None:
        query = query.where(PortfolioPosition.account_id == account_id)
    positions = db.execute(query.order_by(PortfolioPosition.created_at)).scalars().all()

    items: list[dict[str, Any]] = []
    total_cost = 0.0
    total_value = 0.0
    for pos in positions:
        try:
            out = _build_position_out(db, pos)
        except HTTPException:
            continue
        if out is None:
            continue
        total_cost += out.cost_basis
        if out.market_value is not None:
            total_value += out.market_value
        items.append({
            "position_id": out.id,
            "ticker": out.stock.ticker,
            "exchange_code": out.stock.exchange_code,
            "company_name": out.stock.company_name,
            "sector": out.stock.sector,
            "industry": out.stock.industry,
            "quantity": out.quantity,
            "avg_entry_price": out.avg_entry_price,
            "current_price": out.stock.last_close,
            "unrealized_pl_pct": out.unrealized_pl_pct,
            # Kept for backward compat with other consumers of this context
            # (the AI prompt builder ignores these).
            "position_verdict": out.position_verdict,
            "position_confidence": out.position_confidence,
        })

    total_pl = total_value - total_cost
    total_pl_pct = (total_pl / total_cost * 100.0) if total_cost else 0.0
    return {
        "account_id": account_id,
        "positions_count": len(items),
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pl_pct": total_pl_pct,
        "positions": items,
    }


def _prompt_payload(scope: str, context: dict[str, Any]) -> str:
    """Build the JSON payload sent to the LLM.

    Important design choice: the prompt MUST NOT include our system's derived
    signals (composite_score, verdict, RSI, SMAs, analyst_target, etc.). The
    point of asking an LLM is to get an independent second opinion. Feeding
    it our findings turns it into a rubber-stamp.

    What we send instead: just the identifiers (ticker / exchange / company /
    sector) and basic market facts (current price, change %, market cap,
    currency). Recent news headlines are included so the model has a freshness
    signal it couldn't reasonably know about from training data alone. The
    model is then instructed to evaluate the stock using its OWN knowledge
    and reasoning — fundamentals, valuation, sector trends, macro context.
    """
    if scope == "stock":
        stock = context["stock"]
        # Just headlines — no sentiment, no scoring. The model decides what
        # matters and weighs them itself.
        news_headlines = [
            n.get("headline") for n in (stock.get("news") or [])
            if n.get("headline")
        ][:5]
        return json.dumps({
            "task": "Analyze the stock independently. Use your own knowledge of "
                    "the company, sector, valuation norms, macro context, and "
                    "any relevant fundamentals. Do not assume any signals are "
                    "implied by the inputs below — they are identification "
                    "only, not a starting point for the analysis.",
            "output_schema": {
                "ticker": "string",
                "decision": "BUY|HOLD|SELL|WATCH",
                "confidence": "0-100 integer",
                "summary": "short string — the core thesis",
                "thesis": ["brief bullet strings, max 3 — why this decision"],
                "risks": ["brief bullet strings, max 3 — what could go wrong"],
                "action": "short string — what the user should do next",
            },
            "stock_identification": {
                "ticker": stock.get("ticker"),
                "exchange": stock.get("exchange_code"),
                "company": stock.get("company_name"),
                "sector": stock.get("sector"),
                "industry": stock.get("industry"),
                "country": stock.get("country"),
                "currency": stock.get("currency"),
            },
            "current_market_snapshot": {
                "price": stock.get("current_price"),
                "day_change_pct": stock.get("change_pct"),
                "market_cap": stock.get("market_cap"),
            },
            "recent_news_headlines": news_headlines,
            "instructions": [
                "Form your own view using publicly available information you know about.",
                "Do not rely on or repeat back any third-party analyst targets or scores.",
                "If you lack enough information for a confident view, set decision to WATCH and explain why in summary.",
                "Use the fewest possible tokens. No markdown. Return JSON only.",
            ],
        }, separators=(",", ":"))

    # Portfolio scope — same principle: identify each position, give cost
    # basis and current price (so the model knows the user's economics), and
    # let the model evaluate each one on its own merits.
    portfolio = context["portfolio"]
    positions_out = []
    for p in portfolio.get("positions") or []:
        positions_out.append({
            "ticker": p.get("ticker"),
            "exchange": p.get("exchange_code"),
            "company": p.get("company_name"),
            "sector": p.get("sector"),
            "industry": p.get("industry"),
            "quantity": p.get("quantity"),
            "avg_entry_price": p.get("avg_entry_price"),
            "current_price": p.get("current_price"),
            "unrealized_pl_pct": p.get("unrealized_pl_pct"),
            # NOTE: position_verdict deliberately omitted — that's our system's
            # opinion, the model should form its own.
        })

    return json.dumps({
        "task": "Analyze the portfolio and each position independently. Use "
                "your own knowledge of each company, sector, current valuation, "
                "and macro context. Identify concentration risk, "
                "diversification gaps, and per-position rebalancing actions. "
                "Do not assume any signals are implied by the inputs below.",
        "output_schema": {
            "portfolio_view": "HOLD|BUY_MORE|SELL|TRIM",
            "confidence": "0-100 integer",
            "summary": "short string — overall portfolio thesis",
            "risks": ["brief bullet strings, max 3 — portfolio-level risks"],
            "actions": ["brief bullet strings, max 3 — recommended changes"],
            "positions": [
                {
                    "ticker": "string",
                    "decision": "HOLD|BUY_MORE|SELL|TRIM|STOP_LOSS",
                    "confidence": "0-100 integer",
                    "reason": "short string — independent rationale",
                }
            ],
        },
        "portfolio_snapshot": {
            "positions_count": portfolio.get("positions_count"),
            "total_cost": portfolio.get("total_cost"),
            "total_value": portfolio.get("total_value"),
            "total_pl_pct": portfolio.get("total_pl_pct"),
        },
        "positions": positions_out,
        "instructions": [
            "Form your own view per position using publicly available information you know about.",
            "Consider sector diversification and concentration risk for the portfolio view.",
            "Use the fewest possible tokens. No markdown. Return JSON only.",
        ],
    }, separators=(",", ":"))


def _finish_reason(provider_key: str, payload: dict[str, Any]) -> Optional[str]:
    """Pull the finish_reason / stop reason from the provider payload, if any.

    A reason of 'MAX_TOKENS' / 'length' means the model hit its output cap
    mid-response. We surface that as a distinct error so the operator knows
    to bump max_output_tokens (or turn off Gemini thinking).
    """
    if provider_key in {"openai", "xai"}:
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            return choices[0].get("finish_reason")
    if provider_key == "anthropic":
        return payload.get("stop_reason")
    if provider_key == "gemini":
        candidates = payload.get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            return candidates[0].get("finishReason") or candidates[0].get("finish_reason")
    return None


def _attempt_repair_truncated_json(text: str) -> Optional[str]:
    """Best-effort fix for JSON that ran out of tokens mid-response.

    Walks the text tracking string/escape state and bracket depth, then
    closes any unterminated string and appends the closing brackets/braces
    in the right order. Returns None if the partial doesn't look salvageable
    (e.g. it doesn't even contain a key:value pair we could keep).

    This is a hail-mary so the user gets *something* back rather than a hard
    fail. Garbage in, less-garbage out — the operator should still bump the
    token cap if this fires often.
    """
    if not text:
        return None
    stack: list[str] = []  # 'object' or 'array'
    in_string = False
    escape = False
    last_non_ws = ""
    for ch in text:
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("object")
        elif ch == "[":
            stack.append("array")
        elif ch == "}" and stack and stack[-1] == "object":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "array":
            stack.pop()
        if not ch.isspace():
            last_non_ws = ch

    # Nothing to close, or never even opened anything — give up.
    if not stack and not in_string:
        return text if text.strip() else None
    if not stack and in_string:
        # A bare unterminated string isn't repairable into a JSON object.
        return None

    repaired = text
    # Close any unterminated string
    if in_string:
        repaired += '"'
    # If we cut off right after a key opener like `"summary":`, we need a
    # placeholder value before the closer. Heuristic: if the last meaningful
    # char is ':' or ',' we drop the trailing fragment.
    if last_non_ws in (":", ","):
        # Strip back to the last balanced position — easier than guessing
        # what should follow the dangling key.
        idx = max(repaired.rfind(","), repaired.rfind("{"), repaired.rfind("["))
        if idx > 0:
            repaired = repaired[:idx]
    # Close remaining containers in reverse open order.
    closers = {"object": "}", "array": "]"}
    while stack:
        repaired += closers[stack.pop()]
    return repaired


def _parse_response_json(provider_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = _extract_text(payload, provider_key)
    finish = (_finish_reason(provider_key, payload) or "").upper()
    is_truncated = finish in {"MAX_TOKENS", "LENGTH"}

    if not text:
        if is_truncated:
            raise ValueError(
                "Model output was empty because it hit the token limit "
                "before producing visible text (likely Gemini thinking "
                "consumed the whole budget). Increase max_output_tokens "
                "on the prompt template."
            )
        raise ValueError("Empty model response")

    cleaned = _sanitize_json_text(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # If the response was cut off mid-JSON we can sometimes patch it
        # enough to extract a partial verdict — better than a hard fail.
        if is_truncated:
            repaired = _attempt_repair_truncated_json(cleaned)
            if repaired:
                try:
                    data = json.loads(repaired)
                    if isinstance(data, dict):
                        data.setdefault(
                            "_warning",
                            "Response was truncated at the token limit and "
                            "auto-repaired. Increase max_output_tokens for "
                            "a complete answer.",
                        )
                        return data
                except json.JSONDecodeError:
                    pass
            raise ValueError(
                "Model response was truncated at the token limit "
                f"(finishReason={finish}). Partial text: {cleaned[:200]}"
            ) from exc
        raise ValueError(f"Model returned non-JSON text: {cleaned[:200]}") from exc

    if not isinstance(data, dict):
        raise ValueError("Model JSON response must be an object")
    return data


@router.get("/providers", response_model=list[AIProviderSettingSeed])
def list_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(AIProviderSetting).where(AIProviderSetting.user_id == user.id)
    ).scalars().all()
    by_key = {r.provider_key: r for r in rows}
    return [_provider_row_out(by_key.get(key), key) for key in PROVIDERS]


@router.put("/providers/{provider_key}", response_model=AIProviderSettingSeed)
def save_provider(
    provider_key: str,
    body: AIProviderSettingUpsertLocal,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if provider_key not in PROVIDERS:
        raise HTTPException(404, f"Unknown AI provider '{provider_key}'")
    row = _upsert_provider(db, user, provider_key, body)
    return _provider_row_out(row, provider_key)


@router.get("/prompts", response_model=list[AIPromptTemplateOut])
def list_prompts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AIPromptTemplate).order_by(AIPromptTemplate.scope, AIPromptTemplate.key)).scalars().all()
    if not rows:
        return [AIPromptTemplateOut(**v) for v in PROMPTS.values()]
    return [AIPromptTemplateOut.model_validate(row) for row in rows]


async def _analyze_many(
    user: User,
    db: Session,
    provider_keys: list[str],
    scope: str,
    prompt_key: str,
    context: dict[str, Any],
) -> list[AIAnalysisResult]:
    prompt = _prompt_payload(scope, context)
    prompt_meta = PROMPTS.get(prompt_key) or PROMPTS["stock_brief"]
    max_tokens = int(prompt_meta["max_output_tokens"])

    rows = db.execute(
        select(AIProviderSetting).where(
            AIProviderSetting.user_id == user.id,
            AIProviderSetting.provider_key.in_(provider_keys),
        )
    ).scalars().all()
    cfg_by_key = {r.provider_key: r for r in rows}

    results: list[AIAnalysisResult] = []
    for key in provider_keys:
        meta = PROVIDERS[key]
        cfg = cfg_by_key.get(key)
        if cfg is None:
            results.append(AIAnalysisResult(
                provider_key=key,
                provider_name=meta["label"],
                model_name=meta["default_model"],
                ok=False,
                error="Provider is not configured",
                latency_ms=None,
                analysis=None,
            ))
            continue
        if not cfg.enabled:
            results.append(AIAnalysisResult(
                provider_key=key,
                provider_name=meta["label"],
                model_name=cfg.model_name or meta["default_model"],
                ok=False,
                error="Provider is disabled",
                latency_ms=None,
                analysis=None,
            ))
            continue
        if not cfg.api_key:
            results.append(AIAnalysisResult(
                provider_key=key,
                provider_name=meta["label"],
                model_name=cfg.model_name or meta["default_model"],
                ok=False,
                error="Missing API key",
                latency_ms=None,
                analysis=None,
            ))
            continue

        started = time.perf_counter()
        try:
            raw = await _call_provider(key, cfg, prompt, max_tokens)
            data = _parse_response_json(key, raw)
            results.append(AIAnalysisResult(
                provider_key=key,
                provider_name=meta["label"],
                model_name=cfg.model_name or meta["default_model"],
                ok=True,
                error=None,
                latency_ms=int((time.perf_counter() - started) * 1000),
                analysis=data,
            ))
        except Exception as exc:
            results.append(AIAnalysisResult(
                provider_key=key,
                provider_name=meta["label"],
                model_name=cfg.model_name or meta["default_model"],
                ok=False,
                error=str(exc),
                latency_ms=int((time.perf_counter() - started) * 1000),
                analysis=None,
            ))
    return results


@router.post("/analyze/stock/{exchange}/{ticker}", response_model=AIAnalysisResponseOut)
async def analyze_stock(
    exchange: str,
    ticker: str,
    body: AIAnalysisRequestBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    context = {"stock": _build_stock_context(db, exchange, ticker)}
    selected = [k for k in (body.provider_keys or []) if k in PROVIDERS]
    if not selected:
        configured = db.execute(
            select(AIProviderSetting.provider_key).where(
                AIProviderSetting.user_id == user.id,
                AIProviderSetting.enabled.is_(True),
                AIProviderSetting.api_key.is_not(None),
                AIProviderSetting.api_key != "",
            )
        ).scalars().all()
        selected = [k for k in configured if k in PROVIDERS]
    if not selected:
        raise HTTPException(400, "No enabled AI providers found. Configure them in Profile first.")

    results = await _analyze_many(user, db, selected, "stock", body.prompt_key, context)
    return AIAnalysisResponseOut(scope="stock", prompt_key=body.prompt_key, context=context, results=results)


@router.post("/analyze/portfolio", response_model=AIAnalysisResponseOut)
async def analyze_portfolio(
    body: AIAnalysisRequestBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    context = {"portfolio": _build_portfolio_context(db, user, body.account_id)}
    selected = [k for k in (body.provider_keys or []) if k in PROVIDERS]
    if not selected:
        configured = db.execute(
            select(AIProviderSetting.provider_key).where(
                AIProviderSetting.user_id == user.id,
                AIProviderSetting.enabled.is_(True),
                AIProviderSetting.api_key.is_not(None),
                AIProviderSetting.api_key != "",
            )
        ).scalars().all()
        selected = [k for k in configured if k in PROVIDERS]
    if not selected:
        raise HTTPException(400, "No enabled AI providers found. Configure them in Profile first.")

    results = await _analyze_many(user, db, selected, "portfolio", body.prompt_key, context)
    return AIAnalysisResponseOut(scope="portfolio", prompt_key=body.prompt_key, context=context, results=results)
