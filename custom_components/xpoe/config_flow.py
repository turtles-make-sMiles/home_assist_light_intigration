"""Config flow for the X-PoE integration."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    XPoEAuthError,
    XPoEClient,
    XPoEConnectionError,
    XPoEError,
)
from .const import (
    CONF_VERIFY_SSL,
    CREDS_DOCS_URL,
    DEFAULT_PORT,
    DEFAULT_SCHEME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

MAC_HEX_RE = re.compile(r"([0-9a-f]{12})", re.IGNORECASE)
XPOE_INSTANCE_PREFIX = "xpoe-"
XPOE_SERVICE_TYPES: tuple[str, ...] = (
    "_xpoe_lighting._tcp.local.",
    "_http._tcp.local.",
)
SCAN_TIMEOUT_SECONDS = 5.0
MANUAL_CHOICE = "manual"

STEP_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)

STEP_CREDS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate(hass, data: dict[str, Any]) -> dict[str, Any]:
    """Log in + fetch /api/info. Raises XPoE* on failure."""
    verify_ssl = data.get(CONF_VERIFY_SSL, False)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = XPoEClient(
        data[CONF_HOST],
        session,
        port=data.get(CONF_PORT, DEFAULT_PORT),
        scheme=DEFAULT_SCHEME,
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        verify_ssl=verify_ssl,
    )
    await client.login()
    info = await client.get_info()
    if not info.get("mac_address"):
        raise XPoEError("device info missing mac_address")
    return info


def _extract_mac(*candidates: str) -> str | None:
    for c in candidates:
        if not c:
            continue
        m = MAC_HEX_RE.search(c)
        if m:
            return m.group(1).lower()
    return None


def _is_xpoe_instance(fqdn: str) -> tuple[bool, str | None]:
    """If fqdn is an xpoe-* instance under one of our service types, return (True, service_type)."""
    lowered = fqdn.lower()
    for svc in XPOE_SERVICE_TYPES:
        suffix = "." + svc
        if lowered.endswith(suffix):
            instance = lowered[: -len(suffix)]
        elif lowered.endswith(svc) and lowered != svc:
            instance = lowered[: -len(svc)]
        else:
            continue
        if instance.startswith(XPOE_INSTANCE_PREFIX):
            return True, svc
    return False, None


async def _scan_for_xpoe(hass, timeout: float = SCAN_TIMEOUT_SECONDS) -> list[dict[str, str]]:
    """Active mDNS browse + cache harvest for X-PoE switches. Returns [{mac_id, host}, ...]."""
    try:
        aiozc = await zeroconf.async_get_async_instance(hass)
    except Exception:
        _LOGGER.exception("Could not get zeroconf instance for scan")
        return []

    # (name_lower -> service_type) so we dedupe browser + cache hits regardless of case.
    seen: dict[str, str] = {}

    # zeroconf invokes handlers via kwargs (zeroconf=, service_type=, name=, state_change=)
    # so the parameter NAMES must match exactly.
    def handler(zeroconf, service_type, name, state_change):
        if state_change is not ServiceStateChange.Added:
            return
        is_xpoe, svc = _is_xpoe_instance(name)
        if is_xpoe and svc:
            seen[name.lower()] = svc

    browser = AsyncServiceBrowser(aiozc.zeroconf, list(XPOE_SERVICE_TYPES), handlers=[handler])
    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()

    # Belt-and-suspenders: harvest anything HA has already cached.
    try:
        for cached in aiozc.zeroconf.cache.names():
            is_xpoe, svc = _is_xpoe_instance(cached)
            if is_xpoe and svc:
                seen.setdefault(cached.lower(), svc)
    except Exception:
        _LOGGER.debug("could not enumerate zeroconf cache", exc_info=True)

    _LOGGER.info(
        "X-PoE mDNS scan: discovered %d instance(s) in %.1fs: %s",
        len(seen),
        timeout,
        sorted(seen),
    )

    # Resolve each and dedupe by MAC (first resolve wins; xpoe_lighting listed before http
    # so it takes precedence when both exist).
    by_mac: dict[str, dict[str, str]] = {}
    for name, svc in seen.items():
        info = AsyncServiceInfo(svc, name)
        try:
            ok = await info.async_request(aiozc.zeroconf, 2000)
        except Exception:
            _LOGGER.exception("Failed to resolve %s", name)
            continue
        if not ok:
            _LOGGER.warning("X-PoE mDNS resolve failed (no response): %s", name)
            continue
        addrs = info.parsed_addresses() or []
        ipv4 = [a for a in addrs if ":" not in a]
        host = (ipv4 or addrs or [None])[0]
        if not host:
            _LOGGER.warning("X-PoE mDNS resolve returned no address: %s", name)
            continue
        mac_id = _extract_mac(name, info.server or "")
        if not mac_id:
            _LOGGER.warning("X-PoE mDNS could not extract MAC from name: %s", name)
            continue
        if mac_id not in by_mac:
            by_mac[mac_id] = {"mac_id": mac_id, "host": host, "name": name}

    results = list(by_mac.values())
    _LOGGER.info(
        "X-PoE mDNS scan: %d unique switch(es) usable after resolve+dedupe: %s",
        len(results),
        [(r["mac_id"], r["host"]) for r in results],
    )
    return results


class XPoEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for X-PoE."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: list[dict[str, str]] = []
        self._scan_done = False
        self._scan_status = ""
        self._discovered_host: str | None = None
        self._discovered_mac: str | None = None

    def _unconfigured_only(self) -> list[dict[str, str]]:
        configured = {entry.unique_id for entry in self._async_current_entries()}
        return [d for d in self._discovered if d["mac_id"] not in configured]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry: scan, then either show picker or fall through to manual."""
        if not self._scan_done:
            self._scan_done = True
            self._discovered = await _scan_for_xpoe(self.hass)

        available = self._unconfigured_only()
        total_seen = len(self._discovered)
        configured_seen = total_seen - len(available)
        if total_seen == 0:
            self._scan_status = "0 X-PoE switches found on the network"
        elif configured_seen:
            self._scan_status = (
                f"{len(available)} new + {configured_seen} already-configured X-PoE switch(es) found"
            )
        else:
            self._scan_status = f"{len(available)} X-PoE switch(es) found on the network"

        if not available:
            return await self.async_step_manual()

        if user_input is not None:
            choice = user_input["device"]
            if choice == MANUAL_CHOICE:
                return await self.async_step_manual()
            for d in available:
                if d["mac_id"] == choice:
                    await self.async_set_unique_id(d["mac_id"])
                    self._abort_if_unique_id_configured(updates={CONF_HOST: d["host"]})
                    self._discovered_host = d["host"]
                    self._discovered_mac = d["mac_id"]
                    self.context["title_placeholders"] = {
                        "name": f"X-PoE ({d['mac_id'][-4:].upper()})"
                    }
                    return await self.async_step_creds()
            return await self.async_step_manual()

        options = [
            SelectOptionDict(
                value=d["mac_id"],
                label=f"X-PoE ({d['mac_id'][-4:].upper()}) — {d['host']}",
            )
            for d in available
        ]
        options.append(SelectOptionDict(value=MANUAL_CHOICE, label="Enter IP manually"))

        schema = vol.Schema(
            {
                vol.Required("device"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"scan_status": self._scan_status},
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate(self.hass, user_input)
            except XPoEAuthError:
                errors["base"] = "invalid_auth"
            except XPoEConnectionError:
                errors["base"] = "cannot_connect"
            except XPoEError as err:
                _LOGGER.exception("Unexpected error during config validation: %s", err)
                errors["base"] = "unknown"
            else:
                mac_id = info["mac_address"].replace(":", "").lower()
                await self.async_set_unique_id(mac_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(
                    title=f"X-PoE ({mac_id[-4:].upper()})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_MANUAL_SCHEMA,
            description_placeholders={
                "scan_status": self._scan_status,
                "creds_docs": CREDS_DOCS_URL,
            },
            errors=errors,
        )

    async def async_step_creds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Just username/password for a device whose host we already know."""
        assert self._discovered_host and self._discovered_mac
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_HOST: self._discovered_host,
                CONF_PORT: DEFAULT_PORT,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_VERIFY_SSL: False,
            }
            try:
                await _validate(self.hass, data)
            except XPoEAuthError:
                errors["base"] = "invalid_auth"
            except XPoEConnectionError:
                errors["base"] = "cannot_connect"
            except XPoEError as err:
                _LOGGER.exception("Unexpected error during creds validation: %s", err)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"X-PoE ({self._discovered_mac[-4:].upper()})",
                    data=data,
                )

        return self.async_show_form(
            step_id="creds",
            data_schema=STEP_CREDS_SCHEMA,
            description_placeholders={
                "host": self._discovered_host,
                "mac": self._discovered_mac,
                "creds_docs": CREDS_DOCS_URL,
            },
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle an X-PoE switch discovered by HA's passive mDNS."""
        mac_id = _extract_mac(discovery_info.hostname or "", discovery_info.name or "")
        if not mac_id:
            return self.async_abort(reason="not_xpoe_device")

        await self.async_set_unique_id(mac_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.host})

        self._discovered_host = discovery_info.host
        self._discovered_mac = mac_id
        self.context["title_placeholders"] = {"name": f"X-PoE ({mac_id[-4:].upper()})"}
        return await self.async_step_creds()
