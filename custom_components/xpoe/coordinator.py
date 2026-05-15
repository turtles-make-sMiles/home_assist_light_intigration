"""DataUpdateCoordinator for X-PoE switches."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import XPoEClient, XPoEError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class XPoEDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One poll per cycle: GET /api/level + GET /api/info in parallel."""

    def __init__(self, hass: HomeAssistant, client: XPoEClient, mac_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{mac_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.mac_id = mac_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            levels, info = await asyncio.gather(
                self.client.get_levels(),
                self.client.get_info(),
            )
        except XPoEError as err:
            raise UpdateFailed(f"X-PoE poll failed: {err}") from err
        return {"levels": levels, "info": info}

    def port_level(self, port_number: int) -> float:
        """Average level (0-100) of the port's two channels, from GET /api/level."""
        levels = self.data.get("levels", {}) if self.data else {}
        keys = (f"channel_{port_number * 2 - 1:02d}", f"channel_{port_number * 2:02d}")
        vals = [float(levels[k]["level"]) for k in keys if k in levels]
        return sum(vals) / len(vals) if vals else 0.0
