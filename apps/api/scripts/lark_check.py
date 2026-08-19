"""Standalone Lark connection check — token exchange, chat discovery, and a
real test card, without booting the API.

Deliberately dependency-light: it reads the same `HAALAND_*` settings the
app does but touches neither Postgres nor Redis, so it is usable as the very
first step of onboarding a Lark organisation, before any infrastructure is
up. Every step prints what it proved and what it did not, because "the send
failed" is the least useful thing a Lark integration can tell you.

    python scripts/lark_check.py                 # verify + list chats
    python scripts/lark_check.py --send          # ... and post a test card
    python scripts/lark_check.py --send --target oc_xxx

Exit code 0 only if every attempted step succeeded.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from haaland.config import get_settings
from haaland.domain.models import NotificationMessage
from haaland.integrations.base import NotificationError
from haaland.integrations.notify.lark import LarkAppClient, LarkAppNotifier, LarkWebhookNotifier


def _ok(step: str, detail: str = "") -> None:
    print(f"  [ok]   {step}{' - ' + detail if detail else ''}")


def _fail(step: str, detail: str) -> None:
    print(f"  [fail] {step} - {detail}")


def _test_message(target: str | None) -> NotificationMessage:
    return NotificationMessage(
        kind="test",
        title="Agent Haaland — Lark connection check",
        body_markdown=(
            "This card was sent by `scripts/lark_check.py`.\n"
            "If you can read it, outbound notifications are wired correctly."
        ),
        target=target,
    )


async def _check_app_mode(settings, *, send: bool, target: str | None) -> int:
    if not (settings.lark_app_id and settings.lark_app_secret):
        _fail("credentials", "HAALAND_LARK_APP_ID / HAALAND_LARK_APP_SECRET are not set")
        return 1

    client = LarkAppClient(settings.lark_app_id, settings.lark_app_secret, domain=settings.lark_domain)
    failures = 0

    try:
        info = await client.verify_credentials()
        _ok("tenant_access_token", f"{info['app_id']} @ {info['base_url']}")
    except NotificationError as exc:
        _fail("tenant_access_token", str(exc))
        # Nothing downstream can work without a token.
        return 1

    try:
        chats = await client.list_chats()
        if chats:
            _ok(f"bot is in {len(chats)} chat(s)")
            for chat in chats:
                print(f"         {chat['chat_id']}  {chat['name']}")
        else:
            _ok("chat list", "empty - add the bot to a group chat (Settings -> Bots -> Add Bot)")
    except NotificationError as exc:
        # A missing im:chat:readonly scope fails here but does not block sending.
        _fail("list chats", str(exc))
        failures += 1

    if not send:
        return failures

    destination = target or settings.lark_default_receive_id
    if not destination:
        _fail("send test card", "no --target and no HAALAND_LARK_DEFAULT_RECEIVE_ID")
        return failures + 1

    notifier = LarkAppNotifier(
        client, destination, default_receive_id_type=settings.lark_default_receive_id_type
    )
    try:
        message_id = await notifier.send(_test_message(None))
        _ok("send test card", f"message_id={message_id} -> {destination}")
    except NotificationError as exc:
        _fail("send test card", str(exc))
        failures += 1

    return failures


async def _check_webhook_mode(settings, *, send: bool) -> int:
    if not settings.lark_webhook_url:
        _fail("webhook url", "HAALAND_LARK_WEBHOOK_URL is not set")
        return 1
    _ok("webhook url", settings.lark_webhook_url.split("/hook/")[0] + "/hook/...")
    if not send:
        print("  (custom webhook bots expose no read API - rerun with --send to test delivery)")
        return 0

    notifier = LarkWebhookNotifier(settings.lark_webhook_url, settings.lark_webhook_secret)
    try:
        ref = await notifier.send(_test_message(None))
        _ok("send test card", f"ref={ref}")
    except NotificationError as exc:
        _fail("send test card", str(exc))
        return 1
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Lark connection end to end.")
    parser.add_argument("--send", action="store_true", help="actually post a test card")
    parser.add_argument(
        "--target",
        help="override the destination for --send: chat_id (oc_...), open_id (ou_...) or work email",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"lark mode={settings.lark_mode} domain={settings.lark_domain}")
    if "lark" not in settings.notify_channel_list:
        print("  note: 'lark' is not in HAALAND_NOTIFY_CHANNELS - the app will not notify at runtime")

    if settings.lark_mode == "app":
        failures = await _check_app_mode(settings, send=args.send, target=args.target)
    else:
        failures = await _check_webhook_mode(settings, send=args.send)

    print("PASS" if failures == 0 else f"FAIL ({failures} step(s))")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
