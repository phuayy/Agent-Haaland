"""Lark Open Platform REST client for a **tenant (internal) application** —
the org-wide half of the Lark integration.

Why this exists next to the custom-bot webhook: a custom bot is a per-chat
URL with no identity in the organisation. An internal application is
installed once into the Lark tenant, so it can post into any chat it has
been added to, direct-message a person by open_id/email, edit a card it
already posted, and (once docs/11 §4 lands) receive Approve/Reject taps.
That is what "connected to the organisation" means in Lark's model.

Auth is a `tenant_access_token`, exchanged from app_id/app_secret and valid
~2h. It is cached in-process behind an asyncio.Lock and refreshed with a
5-minute margin — deliberately the same shape as the GitHub App installation
token cache in integrations/scm/auth.py, including the "refresh once, retry
once" reaction to a token the server rejects mid-flight.

Raw httpx over the handful of endpoints we use, no SDK: the official
`lark-oapi` package pulls in a large surface area for what is four calls,
and docs/02's SDK rule is explicit about that trade-off."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

import httpx

from haaland.integrations.base import NotificationError

#: How a `receive_id` should be interpreted by Lark's im/v1 message API.
ReceiveIdType = Literal["chat_id", "open_id", "user_id", "union_id", "email"]

#: Lark runs two physically separate clouds with separate app registries;
#: an app_id issued on one is meaningless on the other.
BASE_URL_BY_DOMAIN: dict[str, str] = {
    "global": "https://open.larksuite.com",  # Lark / international
    "feishu": "https://open.feishu.cn",  # Feishu / China
}

_TOKEN_REFRESH_MARGIN_SECONDS = 300
#: Lark's "your tenant_access_token is expired/invalid" family. Any of these
#: means: mint a new token and retry the call exactly once.
_INVALID_TOKEN_CODES = frozenset({99991661, 99991663, 99991664, 99991665})


class LarkAPIError(NotificationError):
    """A Lark API call failed. Subclasses NotificationError so a failure on
    the notification path is caught by NotificationService like any other
    channel failure (one dead channel must never fail an incident), while
    operator-facing routes can still map it to a 502 specifically."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class LarkAppClient:
    """Thin, typed wrapper over the Lark endpoints this product needs.

    Stateless with respect to messages; the only state is the cached
    tenant_access_token, which is safe to share process-wide (one instance
    lives on the process-wide `Deps`)."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        domain: str = "global",
        timeout_seconds: float = 10.0,
    ) -> None:
        if domain not in BASE_URL_BY_DOMAIN:
            raise ValueError(
                f"unknown lark domain {domain!r}; expected one of {sorted(BASE_URL_BY_DOMAIN)}"
            )
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = BASE_URL_BY_DOMAIN[domain]
        self._timeout = timeout_seconds
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def app_id(self) -> str:
        return self._app_id

    # ----------------------------------------------------------------- auth

    async def tenant_access_token(self, *, force_refresh: bool = False) -> str:
        """Cached token exchange. The lock stops N concurrent notifications
        from minting N tokens on a cold start."""
        async with self._token_lock:
            now = time.time()
            if (
                not force_refresh
                and self._token
                and now < self._token_expiry - _TOKEN_REFRESH_MARGIN_SECONDS
            ):
                return self._token

            body = await self._request(
                "POST",
                "/open-apis/auth/v3/tenant_access_token/internal",
                json_body={"app_id": self._app_id, "app_secret": self._app_secret},
                envelope_field=None,
            )
            token = body.get("tenant_access_token")
            if not token:
                raise LarkAPIError(f"lark returned no tenant_access_token: {body}")
            self._token = str(token)
            self._token_expiry = now + float(body.get("expire", 7200))
            return self._token

    async def verify_credentials(self) -> dict:
        """Cheapest possible proof that app_id/app_secret/domain are right.
        Returns non-secret facts for the operator-facing diagnostics route —
        never the token itself."""
        await self.tenant_access_token(force_refresh=True)
        return {
            "app_id": self._app_id,
            "base_url": self._base_url,
            "token_expires_in_seconds": int(max(0.0, self._token_expiry - time.time())),
        }

    # -------------------------------------------------------------- request

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict[str, Any] | None = None,
        token: str | None = None,
        envelope_field: str | None = "data",
    ) -> dict:
        """One HTTP call. Lark reports application errors as `code != 0`
        inside an HTTP 200, so the code check comes first and the status
        check second — an HTTP-only check would silently accept failures.

        The token endpoint returns its payload at the envelope root rather
        than under `data`; `envelope_field=None` selects that shape."""
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, base_url=self._base_url) as client:
                resp = await client.request(
                    method, path, json=json_body, params=params, headers=headers
                )
        except httpx.HTTPError as exc:
            raise LarkAPIError(f"lark api unreachable ({method} {path}): {exc}") from exc

        try:
            body = resp.json()
        except ValueError as exc:
            raise LarkAPIError(
                f"lark api returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}"
            ) from exc

        code = int(body.get("code", 0))
        if code != 0:
            raise LarkAPIError(
                "lark api rejected {} {}: code={} msg={!r}".format(
                    method, path, code, body.get("msg")
                ),
                code=code,
            )
        if resp.status_code >= 400:
            raise LarkAPIError(f"lark api HTTP {resp.status_code} on {method} {path}")

        if envelope_field is None:
            return dict(body)
        return dict(body.get(envelope_field) or {})

    async def _authed(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict:
        """Every authenticated call goes through here so the token-expiry
        retry exists in exactly one place. A cached token can expire between
        the cache check and the call landing; that is a normal race, not an
        error worth surfacing to the caller."""
        token = await self.tenant_access_token()
        try:
            return await self._request(method, path, json_body=json_body, params=params, token=token)
        except LarkAPIError as exc:
            if exc.code not in _INVALID_TOKEN_CODES:
                raise
            token = await self.tenant_access_token(force_refresh=True)
            return await self._request(method, path, json_body=json_body, params=params, token=token)

    # ------------------------------------------------------------- messages

    async def send_card(
        self, receive_id: str, card: dict, *, receive_id_type: ReceiveIdType = "chat_id"
    ) -> str:
        """POST /open-apis/im/v1/messages. Returns the message_id, which is
        what makes a later in-place card update possible.

        Note the encoding quirk: `content` is a JSON **string**, not an
        object, and for `msg_type=interactive` it is the card itself — not
        wrapped in {"card": ...} the way the custom-bot webhook wants it."""
        data = await self._authed(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json_body={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
        )
        message_id = data.get("message_id")
        if not message_id:
            raise LarkAPIError(f"lark accepted the message but returned no message_id: {data}")
        return str(message_id)

    async def update_card(self, message_id: str, card: dict) -> None:
        """PATCH /open-apis/im/v1/messages/{id} — edits a card in place.
        Used to stamp "Approved by @x" onto the original card so the Lark
        thread and the audit chain never tell different stories."""
        await self._authed(
            "PATCH",
            f"/open-apis/im/v1/messages/{message_id}",
            json_body={"content": json.dumps(card, ensure_ascii=False)},
        )

    # ------------------------------------------------------------ directory

    async def list_chats(self, *, page_size: int = 100) -> list[dict]:
        """GET /open-apis/im/v1/chats — the chats this bot is a member of.
        This is the operator's way to discover a `chat_id` without digging
        it out of a Lark URL by hand. Requires the `im:chat:readonly`
        scope."""
        data = await self._authed("GET", "/open-apis/im/v1/chats", params={"page_size": page_size})
        return [
            {
                "chat_id": item.get("chat_id"),
                "name": item.get("name"),
                "description": item.get("description"),
            }
            for item in data.get("items", [])
        ]

    async def open_ids_by_email(self, emails: list[str]) -> dict[str, str]:
        """POST /open-apis/contact/v3/users/batch_get_id — maps work emails
        to open_ids, so a CODEOWNERS login resolved to an email can be
        direct-messaged (docs/11 §4, "resolving who gets notified").
        Requires the `contact:user.id:readonly` scope. Unknown emails are
        omitted rather than raising: a missing mapping is a routing
        fallback, not a failure."""
        if not emails:
            return {}
        data = await self._authed(
            "POST",
            "/open-apis/contact/v3/users/batch_get_id",
            params={"user_id_type": "open_id"},
            json_body={"emails": emails},
        )
        return {
            str(item["email"]): str(item["user_id"])
            for item in data.get("user_list", [])
            if item.get("email") and item.get("user_id")
        }
