"""Binary sensor platform for X-PoE: dry contact (programming override) input."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import XPoEDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bundle = hass.data[DOMAIN][entry.entry_id]
    coordinator: XPoEDataUpdateCoordinator = bundle["coordinator"]
    mac_id: str = bundle["mac_id"]
    mac: str = bundle["mac"]
    async_add_entities([XPoEDryContact(coordinator, mac_id, mac)])


class XPoEDryContact(CoordinatorEntity[XPoEDataUpdateCoordinator], BinarySensorEntity):
    """True when the device's rear-panel dry-contact override input is engaged."""

    _attr_has_entity_name = True
    _attr_name = "Dry contact"

    def __init__(
        self,
        coordinator: XPoEDataUpdateCoordinator,
        mac_id: str,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{mac_id}_dry_contact"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        info = self.coordinator.data.get("info") or {}
        value = info.get("programming_override")
        if value is None:
            return None
        return bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self.coordinator.data is None:
            return None
        info = self.coordinator.data.get("info") or {}
        setting = info.get("override_setting")
        if setting is None:
            return None
        return {"contact_mode": str(setting)}
