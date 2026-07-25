"""DataUpdateCoordinator for a single MSKMiner device."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CannotConnect, MSKMinerAPI
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class MinerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls a single miner via /api/info_app."""

    def __init__(self, hass: HomeAssistant, api: MSKMinerAPI) -> None:
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=f"MSKMiner {api.host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.get_info()
        except CannotConnect as err:
            raise UpdateFailed(str(err)) from err
