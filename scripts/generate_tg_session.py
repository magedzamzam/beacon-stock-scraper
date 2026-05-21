"""One-time helper: generate a Telethon StringSession for the listener.

Run this ONCE on your local machine (NOT in production), interactively:

    pip install telethon==1.36.0
    python scripts/generate_tg_session.py

It asks for your api_id, api_hash, phone number and login code, then prints
a session string. Paste that string into Beacon's admin → settings →
'tgbot.session_string'.

You only need to do this once per phone number. The session string is a
long-lived credential — store it in app_settings (encrypted at rest is
ideal but Beacon's app_settings is plaintext for now; rotate if leaked).

Why not bake this into the listener service? Generating a session is
interactive (Telegram texts you a code) and would block the container at
startup. Better to do it once on a laptop and paste the result.
"""
from __future__ import annotations

import sys


def main():
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("Install telethon first:  pip install telethon==1.36.0", file=sys.stderr)
        sys.exit(1)

    print("Telegram session generator")
    print("==========================")
    print("Get api_id + api_hash from https://my.telegram.org → API development tools")
    print()
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()
        print()
        print("Session string (paste into app_settings → tgbot.session_string):")
        print()
        print(session_string)
        print()
        print("Keep this secret — anyone with this string can read your Telegram.")


if __name__ == "__main__":
    main()
