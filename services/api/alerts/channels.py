"""Notification channels.

Each channel knows:
  - config_schema: keys it expects in alert_channels.config
  - send(): performs the actual notification

All send() implementations swallow exceptions and return (ok, error_msg) so
a misconfigured channel can't crash the alert engine. Errors are recorded
on the alert_events.delivery jsonb per-channel.
"""
from __future__ import annotations

import json
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any


class Channel:
    """Base. Subclasses override config_schema (class attr) and send()."""
    config_schema: list[dict[str, Any]] = []

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def send(self, title: str, body: str | None) -> tuple[bool, str | None]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Email — SMTP. Config: {to, smtp_host, smtp_port, smtp_user, smtp_pass, from}
# Server-wide SMTP env vars are picked up as defaults if config omits them.
# ---------------------------------------------------------------------------
class EmailChannel(Channel):
    config_schema = [
        {"name": "to",         "type": "text", "label": "To (email address)", "required": True},
        {"name": "from",       "type": "text", "label": "From",               "required": False},
        {"name": "smtp_host",  "type": "text", "label": "SMTP host",          "required": False},
        {"name": "smtp_port",  "type": "number", "label": "SMTP port",        "required": False, "default": 587},
        {"name": "smtp_user",  "type": "text", "label": "SMTP user",          "required": False},
        {"name": "smtp_pass",  "type": "password", "label": "SMTP password",  "required": False},
    ]

    def send(self, title: str, body: str | None) -> tuple[bool, str | None]:
        import os
        to = self.config.get("to")
        if not to:
            return False, "missing 'to' in channel config"
        host = self.config.get("smtp_host") or os.environ.get("SMTP_HOST")
        port = int(self.config.get("smtp_port") or os.environ.get("SMTP_PORT") or 587)
        user = self.config.get("smtp_user") or os.environ.get("SMTP_USER")
        pwd  = self.config.get("smtp_pass") or os.environ.get("SMTP_PASS")
        sender = self.config.get("from") or os.environ.get("SMTP_FROM") or user
        if not host or not sender:
            return False, "missing SMTP host or sender"

        msg = EmailMessage()
        msg["Subject"] = title[:200]
        msg["From"] = sender
        msg["To"] = to
        msg.set_content(body or title)

        try:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls()
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
            return True, None
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Telegram — config: {bot_token, chat_id}
# ---------------------------------------------------------------------------
class TelegramChannel(Channel):
    config_schema = [
        {"name": "bot_token", "type": "password", "label": "Bot token", "required": True},
        {"name": "chat_id",   "type": "text",     "label": "Chat ID",   "required": True},
    ]

    def send(self, title: str, body: str | None) -> tuple[bool, str | None]:
        token = self.config.get("bot_token")
        chat_id = self.config.get("chat_id")
        if not token or not chat_id:
            return False, "missing bot_token or chat_id"
        #text_body = f"*{title}*\n\n{body or ''}".strip()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text_body[:4000],
            # "parse_mode": "Markdown",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True, None
                return False, f"telegram returned {resp.status}: {resp.read()[:200].decode('utf-8', 'replace')}"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Webhook — POST JSON {title, body, snapshot}. Config: {url, headers}
# ---------------------------------------------------------------------------
class WebhookChannel(Channel):
    config_schema = [
        {"name": "url",     "type": "text",     "label": "URL", "required": True},
        {"name": "headers", "type": "textarea", "label": "Extra headers (JSON object, optional)", "required": False},
    ]

    def send(self, title: str, body: str | None) -> tuple[bool, str | None]:
        url = self.config.get("url")
        if not url:
            return False, "missing url"
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        raw_h = self.config.get("headers")
        if raw_h:
            try:
                extra = json.loads(raw_h) if isinstance(raw_h, str) else raw_h
                if isinstance(extra, dict):
                    headers.update({k: str(v) for k, v in extra.items()})
            except Exception:
                pass  # malformed header config — fall through with defaults
        try:
            req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True, None
                return False, f"webhook returned {resp.status}"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# SMS via Twilio. Config: {twilio_sid, twilio_token, from, to}
# Optional: real Twilio integration would use their SDK but we keep this
# dependency-light with their REST API directly.
# ---------------------------------------------------------------------------
class SmsChannel(Channel):
    config_schema = [
        {"name": "twilio_sid",   "type": "text",     "label": "Twilio Account SID", "required": True},
        {"name": "twilio_token", "type": "password", "label": "Twilio Auth Token",  "required": True},
        {"name": "from",         "type": "text",     "label": "From (+1...)",       "required": True},
        {"name": "to",           "type": "text",     "label": "To (+1...)",         "required": True},
    ]

    def send(self, title: str, body: str | None) -> tuple[bool, str | None]:
        import base64
        sid = self.config.get("twilio_sid")
        token = self.config.get("twilio_token")
        sender = self.config.get("from")
        to = self.config.get("to")
        if not all((sid, token, sender, to)):
            return False, "missing twilio credentials"
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        text_body = f"{title}\n{body or ''}".strip()[:1500]
        data = urllib.parse.urlencode({
            "From": sender, "To": to, "Body": text_body,
        }).encode("utf-8")
        auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
        try:
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Authorization": f"Basic {auth}",
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True, None
                return False, f"twilio returned {resp.status}: {resp.read()[:200].decode('utf-8', 'replace')}"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"


CHANNEL_REGISTRY: dict[str, type[Channel]] = {
    "email":    EmailChannel,
    "telegram": TelegramChannel,
    "webhook":  WebhookChannel,
    "sms":      SmsChannel,
}

_CHANNEL_LABELS = {
    "email":    "Email",
    "telegram": "Telegram",
    "webhook":  "Webhook",
    "sms":      "SMS (Twilio)",
}


def get_channel_meta() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": _CHANNEL_LABELS.get(key, key),
            "config_schema": cls.config_schema,
        }
        for key, cls in CHANNEL_REGISTRY.items()
    ]
