"""The X-PoE integration.

HA-specific imports are guarded so this package can also be imported from
plain tooling (e.g. `xpoe_api/smoke_test.py`) without Home Assistant installed.
"""
from __future__ import annotations

import logging

from .const import DOMAIN  # noqa: F401  re-exported for tooling

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import (
        CONF_HOST,
        CONF_PASSWORD,
        CONF_PORT,
        CONF_USERNAME,
    )
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
except ImportError:
    pass
else:
    from .api import XPoEClient, XPoEConnectionError, XPoEError
    from .const import (
        CONF_VERIFY_SSL,
        DEFAULT_PORT,
        DEFAULT_SCHEME,
        HW_MODEL_MAP,
        PLATFORMS,
    )
    from .coordinator import XPoEDataUpdateCoordinator

    async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Set up X-PoE from a config entry."""
        data = entry.data
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

        try:
            info = await client.get_info()
        except XPoEConnectionError as err:
            raise ConfigEntryNotReady(f"Cannot reach X-PoE at {data[CONF_HOST]}: {err}") from err
        except XPoEError as err:
            raise ConfigEntryNotReady(f"X-PoE setup failed: {err}") from err

        mac = info.get("mac_address")
        if not mac:
            raise ConfigEntryNotReady("X-PoE /api/info returned no mac_address")

        mac_id = mac.replace(":", "").lower()
        hw_model_raw = info.get("hw_version", {}).get("model", "")
        model = HW_MODEL_MAP.get(hw_model_raw, hw_model_raw or "X-PoE")

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, mac_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Amatis",
            model=model,
            sw_version=info.get("xpoe_version"),
            name=entry.title,
            configuration_url=f"https://{info.get('local_ipv4', data[CONF_HOST])}",
        )

        coordinator = XPoEDataUpdateCoordinator(hass, client, mac_id)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "client": client,
            "coordinator": coordinator,
            "mac": mac,
            "mac_id": mac_id,
            "info": info,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Unload a config entry."""
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        return unload_ok
