"""Light platform for X-PoE: one entity per physical port."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import channels_for_port
from .const import DEFAULT_FADE_TIME_SECONDS, DOMAIN, NUM_PORTS
from .coordinator import XPoEDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create 8 light entities (one per physical port)."""
    bundle = hass.data[DOMAIN][entry.entry_id]
    coordinator: XPoEDataUpdateCoordinator = bundle["coordinator"]
    mac_id: str = bundle["mac_id"]
    mac: str = bundle["mac"]

    async_add_entities(
        XPoEPortLight(coordinator, entry, mac_id, mac, port)
        for port in range(1, NUM_PORTS + 1)
    )


def _level_to_brightness(level: float) -> int:
    return max(0, min(255, round(level * 255 / 100)))


def _brightness_to_level(brightness: int) -> float:
    return max(0.0, min(100.0, brightness * 100 / 255))


class XPoEPortLight(CoordinatorEntity[XPoEDataUpdateCoordinator], LightEntity):
    """One physical X-PoE port presented as an HA light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: XPoEDataUpdateCoordinator,
        entry: ConfigEntry,
        mac_id: str,
        mac: str,
        port_number: int,
    ) -> None:
        super().__init__(coordinator)
        self._port_number = port_number
        self._channels = channels_for_port(port_number)
        self._last_on_brightness: int | None = None

        self._attr_unique_id = f"{mac_id}_port_{port_number}_light"
        self._attr_name = f"Port {port_number}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        )

    @property
    def _current_level(self) -> float:
        return self.coordinator.port_level(self._port_number)

    def _channel_states(self) -> list[dict[str, Any]]:
        """Return the two channel-state dicts from /api/info for this port."""
        info = (self.coordinator.data or {}).get("info") or {}
        for port in info.get("ports", []):
            if port.get("id") == self._port_number:
                return [ch.get("state") or {} for ch in port.get("channels", [])]
        return []

    def _detection_statuses(self) -> list[str]:
        return [s.get("detection_status", "") for s in self._channel_states()]

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        statuses = self._detection_statuses()
        if not statuses:
            # No detection data yet (pre-first-poll or stripped response).
            # Default to unavailable; first successful poll will flip us on.
            return False
        # All channels report OPEN_CIRCUIT => nothing plugged in => not controllable.
        return not all(s == "OPEN_CIRCUIT" for s in statuses)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self._current_level > 0

    @property
    def brightness(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return _level_to_brightness(self._current_level)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        statuses = self._detection_statuses()
        if not statuses:
            return None
        return {"detection_status": statuses}

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            brightness = self._last_on_brightness or 255
        level = _brightness_to_level(brightness)
        await self.coordinator.client.set_level(
            self._channels, target_level=level, fade_time=DEFAULT_FADE_TIME_SECONDS
        )
        self._last_on_brightness = brightness
        self._push_optimistic_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        current = _level_to_brightness(self._current_level)
        if current > 0:
            self._last_on_brightness = current
        await self.coordinator.client.set_level(
            self._channels, target_level=0, fade_time=DEFAULT_FADE_TIME_SECONDS
        )
        self._push_optimistic_level(0.0)

    def _push_optimistic_level(self, level: float) -> None:
        """Write the just-set level into coordinator.data and reset the poll timer.

        Prevents UI 'popcorning' where a fast poll catches the fade mid-flight
        and bounces the entity state. The next scheduled poll (10s later) will
        deliver the authoritative reading.
        """
        data = dict(self.coordinator.data or {})
        levels = dict(data.get("levels") or {})
        for ch in self._channels:
            key = f"channel_{ch:02d}"
            levels[key] = {"level": level}
        data["levels"] = levels
        self.coordinator.async_set_updated_data(data)

    @callback
    def _handle_coordinator_update(self) -> None:
        current = self.brightness
        if current and current > 0:
            self._last_on_brightness = current
        super()._handle_coordinator_update()
