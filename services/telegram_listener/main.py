"""Telegram listener service.

Listens to Telegram channels configured in tg_channels (is_enabled=true).
For each new message:
    1. Insert into tg_raw_messages with parse_status='pending'
    2. Inline-parse using the channel's parser_key
    3. If parsed, insert into tg_signals and mark raw_message as 'signal'
    4. Otherwise mark raw_message as 'noise'

Reads Telegram credentials from app_settings:
    tgbot.api_id          int   — telegram api_id (from my.telegram.org)
    tgbot.api_hash        str   — telegram api_hash
    tgbot.session_string  str   — Telethon StringSession (created once via
                                  scripts/generate_session.py)

The Telethon client reconnects automatically on network drops. The channel
list is reloaded every 60s so admin changes propagate without restart.

Why Telethon: same library used by the original bot. MTProto is more
forgiving than Bot API and listens to channels we don't own.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, ChatWriteForbiddenError,
)
from telethon.sessions import StringSession

from shared.db import AppSetting, SessionLocal, TgChannel, TgRawMessage, TgSignal
from .parsers import parse as parse_signal


log = logging.getLogger("telegram_listener")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ---------------------------------------------------------------------------
# Configuration access
# ---------------------------------------------------------------------------
def _load_credentials() -> Optional[tuple[int, str, str]]:
    """Read api_id, api_hash, session_string from app_settings.

    Returns None if any of them is missing — the service then sleeps and
    retries (rather than crashing) so admin can configure later without
    redeploying.
    """
    with SessionLocal() as session:
        rows = session.execute(
            select(AppSetting).where(
                AppSetting.key.in_([
                    "tgbot.api_id", "tgbot.api_hash", "tgbot.session_string",
                ])
            )
        ).scalars().all()

    settings = {r.key: r.value for r in rows}
    api_id_raw = settings.get("tgbot.api_id")
    api_hash = settings.get("tgbot.api_hash")
    session_str = settings.get("tgbot.session_string")

    # app_settings stores values as TEXT — coerce api_id to int explicitly so
    # a typo like "123abc" surfaces here, not deep inside Telethon.
    if api_id_raw is None or not api_hash or not session_str:
        return None
    try:
        api_id = int(api_id_raw)
    except ValueError:
        log.error("tgbot.api_id is not an integer: %r", api_id_raw)
        return None
    return api_id, api_hash, session_str


def _load_enabled_channels() -> dict[int, dict]:
    """Return {channel_id: {parser_key, title}} for enabled channels."""
    with SessionLocal() as session:
        rows = session.execute(
            select(TgChannel).where(TgChannel.is_enabled.is_(True))
        ).scalars().all()
    return {
        r.channel_id: {
            "parser_key": r.parser_key,
            "channel_title": r.channel_title,
            "row_id": r.id,
        }
        for r in rows
    }


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------
async def _handle_message(event, channels: dict[int, dict]):
    """Persist the message and try to parse it.

    The 'pending' → 'signal'/'noise' transition is a tiny state machine —
    we always insert with 'pending' first, then attempt parse, then UPDATE.
    Means if the parser crashes the raw message is still on disk and the
    admin can re-run it later from the audit log.
    """
    msg = event.message
    if msg is None or not msg.message:
        return  # photos / stickers / empty edits — nothing to parse

    raw_chat_id = event.chat_id
    if raw_chat_id is None:
        return
    meta = channels.get(raw_chat_id)
    if meta is None:
        # Channel removed from config since the listener subscribed. We don't
        # un-subscribe live; just drop silently.
        return

    parser_key = meta["parser_key"]
    title = meta["channel_title"]
    text = msg.message

    now = datetime.utcnow()
    with SessionLocal() as session:
        # 1) Insert raw row. ON CONFLICT skips re-deliveries from Telegram
        # (rare but happens on reconnect when the client catches up).
        stmt = pg_insert(TgRawMessage).values(
            channel_id=raw_chat_id,
            channel_title=title,
            tg_message_id=msg.id,
            sender_id=getattr(msg.sender_id, "user_id", msg.sender_id)
                       if msg.sender_id else None,
            message_text=text,
            received_at=now,
            parse_status="pending",
        ).on_conflict_do_nothing(index_elements=["channel_id", "tg_message_id"])
        result = session.execute(stmt)
        session.commit()
        # Was it a fresh insert? ON CONFLICT DO NOTHING returns 0 rowcount when
        # the row already existed. In that case skip parsing — we've seen it.
        if result.rowcount == 0:
            return

        # Re-fetch the row to get its id for the FK on tg_signals.
        raw = session.execute(
            select(TgRawMessage).where(
                TgRawMessage.channel_id == raw_chat_id,
                TgRawMessage.tg_message_id == msg.id,
            )
        ).scalar_one()
        raw_id = raw.id

    # 2) Parse outside the DB session — parser is pure CPU.
    parsed = None
    parse_error = None
    try:
        parsed = parse_signal(parser_key, text)
    except Exception as exc:
        parse_error = f"{type(exc).__name__}: {exc}"
        log.exception("parser_crashed", extra={
            "parser_key": parser_key, "raw_id": raw_id,
        })

    # 3) Persist outcome.
    with SessionLocal() as session:
        raw = session.get(TgRawMessage, raw_id)
        if raw is None:
            return
        raw.processed_at = datetime.utcnow()
        if parse_error:
            raw.parse_status = "failed"
            raw.parse_error = parse_error
        elif parsed is None:
            raw.parse_status = "noise"
        else:
            raw.parse_status = "signal"
            # Use UNIQUE(raw_message_id) to guarantee idempotency if a retry
            # races with this insert.
            sig_stmt = pg_insert(TgSignal).values(
                raw_message_id=raw_id,
                channel_id=raw_chat_id,
                channel_title=title,
                signal_time=raw.received_at,
                symbol=parsed.symbol,
                direction=parsed.direction,
                entry_from=parsed.entry_from,
                entry_to=parsed.entry_to,
                sl=parsed.sl,
                tps=parsed.tps,
                parser_key=parser_key,
                status="NEW",
                raw_text=text,
            ).on_conflict_do_nothing(index_elements=["raw_message_id"])
            session.execute(sig_stmt)
            log.info("signal_extracted symbol=%s dir=%s entry=%.2f-%.2f sl=%.2f tps=%s",
                     parsed.symbol, parsed.direction, parsed.entry_from,
                     parsed.entry_to, parsed.sl, parsed.tps)

        # Bump tg_channels.last_message_at for the UI's "channel last seen" column.
        ch_row_id = channels[raw_chat_id]["row_id"]
        ch = session.get(TgChannel, ch_row_id)
        if ch:
            ch.last_message_at = datetime.utcnow()
        session.commit()


# ---------------------------------------------------------------------------
# Channel-reload loop
# ---------------------------------------------------------------------------
async def _reload_loop(client: TelegramClient, state: dict, interval: int = 60):
    """Every `interval` seconds, refresh the enabled-channels dict and
    register the message handler for newly-added channel IDs.

    Telethon's `events.NewMessage(chats=...)` filter is fixed at registration,
    so we use a single handler with no chat filter, and the channel-id
    check inside _handle_message provides the filtering.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            state["channels"] = _load_enabled_channels()
        except Exception:
            log.exception("channel_reload_failed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def amain():
    """Wait until credentials are configured, then run the listener forever."""
    backoff = 5.0
    while True:
        creds = _load_credentials()
        if creds is not None:
            break
        log.warning(
            "telegram credentials missing in app_settings "
            "(tgbot.api_id / tgbot.api_hash / tgbot.session_string) — "
            "retrying in %.0fs", backoff,
        )
        await asyncio.sleep(backoff)
        # Cap the backoff so we don't end up sleeping for an hour.
        backoff = min(backoff * 1.5, 120.0)

    api_id, api_hash, session_str = creds
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    state = {"channels": _load_enabled_channels()}

    @client.on(events.NewMessage())
    async def _on_message(event):
        try:
            await _handle_message(event, state["channels"])
        except FloodWaitError as fw:
            # Telegram rate-limit — log and sleep the suggested seconds.
            log.warning("flood_wait seconds=%s", fw.seconds)
            await asyncio.sleep(fw.seconds + 1)
        except (ChannelPrivateError, ChatWriteForbiddenError) as exc:
            log.warning("channel_access_error %s", exc)
        except Exception:
            log.exception("handle_message_failed")

    await client.start()
    log.info(
        "telegram_listener_started channels=%d",
        len(state["channels"]),
    )

    # Background channel reloader runs alongside the listener.
    reload_task = asyncio.create_task(_reload_loop(client, state))
    try:
        await client.run_until_disconnected()
    finally:
        reload_task.cancel()


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        log.info("shutdown")
        sys.exit(0)


if __name__ == "__main__":
    main()
