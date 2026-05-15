"""Sensor platform for X-PoE: per-channel power, device voltage + total power."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_PORTS
from .coordinator import XPoEDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class XPoESensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor against the coordinator data."""

    value_fn: Callable[[dict[str, Any]], float | None]


def _port_power(info: dict[str, Any], port_number: int) -> float | None:
    """Sum of both channels' power for a physical port."""
    for port in info.get("ports", []):
        if port.get("id") != port_number:
            continue
        total = 0.0
        any_seen = False
        for ch in port.get("channels", []):
            p = ch.get("power")
            if p is not None:
                total += float(p)
                any_seen = True
        return total if any_seen else port.get("power")
    return None


DEVICE_SENSORS: tuple[XPoESensorDescription, ...] = (
    XPoESensorDescription(
        key="voltage",
        translation_key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda info: info.get("voltage"),
    ),
    XPoESensorDescription(
        key="power",
        translation_key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda info: info.get("power"),
    ),
)


def _port_power_description(port_number: int) -> XPoESensorDescription:
    return XPoESensorDescription(
        key=f"port_{port_number}_power",
        name=f"Port {port_number} power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda info, p=port_number: _port_power(info, p),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bundle = hass.data[DOMAIN][entry.entry_id]
    coordinator: XPoEDataUpdateCoordinator = bundle["coordinator"]
    mac_id: str = bundle["mac_id"]
    mac: str = bundle["mac"]

    entities: list[XPoESensor] = [
        XPoESensor(coordinator, mac_id, mac, desc) for desc in DEVICE_SENSORS
    ]
    for port_num in range(1, NUM_PORTS + 1):
        entities.append(XPoESensor(coordinator, mac_id, mac, _port_power_description(port_num)))

    async_add_entities(entities)


class XPoESensor(CoordinatorEntity[XPoEDataUpdateCoordinator], SensorEntity):
    """Generic X-PoE sensor driven by a description's value_fn."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: XPoEDataUpdateCoordinator,
        mac_id: str,
        mac: str,
        description: XPoESensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        info = self.coordinator.data.get("info") or {}
        return self.entity_description.value_fn(info)
