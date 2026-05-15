"""Async client for the X-PoE switch local REST API."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import ssl
import time
from typing import Any

import aiohttp

from .const import (
    DEFAULT_FADE_TIME_SECONDS,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_SCHEME,
    DEFAULT_USERNAME,
    EXP_SKEW_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class XPoEError(Exception):
    """Base error."""


class XPoEAuthError(XPoEError):
    """Authentication failed."""


class XPoEConnectionError(XPoEError):
    """Network / transport error."""


def _decode_jwt_exp(token: str) -> int:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload))["exp"])


def _make_insecure_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class XPoEClient:
    """Async X-PoE API client.

    Token pair is held in memory. Consumers persist via their own mechanism
    (e.g. HA's Store) and re-hydrate by calling `set_tokens()` after construction.
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        port: int = DEFAULT_PORT,
        scheme: str = DEFAULT_SCHEME,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        verify_ssl: bool = False,
        request_timeout: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._scheme = scheme
        self._username = username
        self._password = password
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._ssl: ssl.SSLContext | bool = True if verify_ssl else _make_insecure_ssl_context()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}"

    @property
    def tokens(self) -> dict[str, str | None]:
        return {"access_token": self._access_token, "refresh_token": self._refresh_token}

    def set_tokens(self, access_token: str | None, refresh_token: str | None) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=body,
                ssl=self._ssl,
                timeout=self._timeout,
            ) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise XPoEAuthError(f"401 on {method} {path}: {text}")
                if resp.status >= 400:
                    raise XPoEError(f"HTTP {resp.status} on {method} {path}: {text}")
                parsed = json.loads(text) if text else {}
                meta_status = parsed.get("meta", {}).get("status")
                errors = parsed.get("errors") or []
                if meta_status and meta_status >= 400:
                    if meta_status == 401:
                        raise XPoEAuthError(
                            f"meta.status=401 on {method} {path}: {errors or text}"
                        )
                    raise XPoEError(
                        f"meta.status={meta_status} on {method} {path}: {errors or text}"
                    )
                if errors:
                    raise XPoEError(f"errors on {method} {path}: {errors}")
                return parsed
        except aiohttp.ClientError as err:
            raise XPoEConnectionError(f"Transport error on {method} {path}: {err}") from err
        except asyncio.TimeoutError as err:
            raise XPoEConnectionError(f"Timeout on {method} {path}") from err

    def _extract_tokens(self, resp: dict[str, Any]) -> tuple[str, str | None]:
        data = resp.get("data") or resp
        access = data.get("access_token") or data.get("token")
        refresh = data.get("refresh_token")
        if not access:
            raise XPoEAuthError(f"login OK but no access_token in response: {resp}")
        return access, refresh

    async def login(self) -> None:
        resp = await self._raw_request(
            "POST",
            "/api/login",
            body={"username": self._username, "password": self._password},
        )
        access, refresh = self._extract_tokens(resp)
        self._access_token = access
        self._refresh_token = refresh

    async def refresh(self) -> None:
        if not self._refresh_token:
            raise XPoEAuthError("no refresh token available")
        resp = await self._raw_request("POST", "/api/refresh", token=self._refresh_token)
        access, refresh = self._extract_tokens(resp)
        self._access_token = access
        if refresh:
            self._refresh_token = refresh

    async def _ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token:
            try:
                if _decode_jwt_exp(self._access_token) - EXP_SKEW_SECONDS > now:
                    return self._access_token
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        if self._refresh_token:
            try:
                if _decode_jwt_exp(self._refresh_token) - EXP_SKEW_SECONDS > now:
                    try:
                        await self.refresh()
                        return self._access_token  # type: ignore[return-value]
                    except XPoEError as err:
                        _LOGGER.debug("Refresh failed, falling back to login: %s", err)
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        await self.login()
        return self._access_token  # type: ignore[return-value]

    async def _authed_request(
        self, method: str, path: str, *, body: Any = None
    ) -> dict[str, Any]:
        async with self._lock:
            token = await self._ensure_access_token()
        try:
            return await self._raw_request(method, path, token=token, body=body)
        except XPoEAuthError:
            async with self._lock:
                await self.login()
                token = self._access_token
            return await self._raw_request(method, path, token=token, body=body)

    async def get_info(self) -> dict[str, Any]:
        resp = await self._authed_request("GET", "/api/info")
        return resp.get("data", resp)

    async def get_levels(self, raw: bool = False) -> dict[str, Any]:
        path = "/api/level?raw_level=1" if raw else "/api/level"
        resp = await self._authed_request("GET", path)
        return resp.get("data", resp)

    async def set_level(
        self,
        channels: list[int],
        target_level: float,
        fade_time: float = DEFAULT_FADE_TIME_SECONDS,
    ) -> dict[str, Any]:
        body = {
            "payload": {
                "channels": channels,
                "target_level": target_level,
                "fade_time": fade_time,
            }
        }
        return await self._authed_request("POST", "/api/level", body=body)

    async def identify(self, duration: int = 30) -> dict[str, Any]:
        """Flash the device's onboard LEDs for `duration` seconds (commissioning aid)."""
        return await self._authed_request(
            "POST", "/api/identify_switch", body={"duration": duration}
        )

    async def identify_channels(
        self, channels: list[int], blink_count: int = 5, sleep: float = 0.5
    ) -> dict[str, Any]:
        """Blink specific channels (useful for fixture-to-port mapping)."""
        body = {"channels": channels, "blink_count": blink_count, "sleep": sleep}
        return await self._authed_request("POST", "/api/identify", body=body)


def channels_for_port(port_number: int) -> list[int]:
    """Map physical port (1-8) to its channel pair (1-16)."""
    return [port_number * 2 - 1, port_number * 2]
