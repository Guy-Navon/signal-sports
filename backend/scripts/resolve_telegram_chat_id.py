"""One-time Telegram chat-id resolution (M7-7, #153). READ-ONLY against Telegram.

Procedure (docs/NOTIFICATIONS.md):
  1. Create the bot with @BotFather and put its token in backend/.env
     (TELEGRAM_BOT_TOKEN). The token is a secret; .env is git-ignored.
  2. Open the bot's chat in Telegram and send it ONE message (anything).
  3. Run:  .venv\\Scripts\\python.exe scripts/resolve_telegram_chat_id.py
  4. Copy the printed chat id into TELEGRAM_CHAT_ID in backend/.env.

Uses the Bot API getUpdates poll — NO webhook is registered, nothing is sent,
and the token is never printed.
"""
from __future__ import annotations

import os
import pathlib
import sys


def main() -> int:
    env_file = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set in backend/.env — do step 1 first.")
        return 1

    import httpx
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
    body = r.json()
    if not body.get("ok"):
        print(f"Telegram refused getUpdates (http {r.status_code}). "
              "Check the token (not printed).")
        return 1

    chats = {}
    for update in body.get("result", []):
        msg = update.get("message") or update.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            chats[chat["id"]] = (chat.get("type"),
                                 chat.get("first_name") or chat.get("title") or "?")

    if not chats:
        print("No messages found. Open the bot's chat in Telegram, send it one "
              "message, then run this again.")
        return 1

    print("Chats that have messaged the bot:")
    for cid, (ctype, name) in chats.items():
        print(f"  chat_id={cid}  type={ctype}  name={name}")
    print("\nCopy the PRIVATE chat id above into TELEGRAM_CHAT_ID in backend/.env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
