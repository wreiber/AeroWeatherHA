from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_ICAOS, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
BASE = "https://aviationweather.gov/api/data"


def _row_icao(row: dict[str, Any]) -> str | None:
    icao = row.get("icaoId") or row.get("stationId") or row.get("station") or row.get("id") or row.get("icao")
    if not icao:
        return None
    return str(icao).upper().strip()


class AeroWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.session: ClientSession = async_get_clientsession(hass)

        data = {**entry.data, **(entry.options or {})}
        self.icaos = [
            str(s).upper().strip()
            for s in (data.get(CONF_ICAOS, []) or [])
            if s and str(s).strip()
        ]
        scan = int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan),
            update_method=self._async_update,
        )

    async def _fetch(self, endpoint: str, ids: str) -> list[dict[str, Any]]:
        url = f"{BASE}/{endpoint}"
        try:
            async with self.session.get(url, params={"ids": ids, "format": "json"}, timeout=20) as resp:
                # 204 = no content (common for TAF at some stations)
                if resp.status == 204:
                    return []
                resp.raise_for_status()

                # Some APIs send odd content-types; accept anyway
                payload = await resp.json(content_type=None)

        except (ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"{endpoint} fetch failed: {err}") from err

        # Normalize list vs wrapped dict responses
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]
        if isinstance(payload, dict):
            for key in ("data", "results", endpoint):
                val = payload.get(key)
                if isinstance(val, list):
                    return [p for p in val if isinstance(p, dict)]
        return []

    async def _async_update(self) -> dict[str, Any]:
        if not self.icaos:
            return {"metar": {}, "taf": {}}

        ids = ",".join(self.icaos)
        metars, tafs = await asyncio.gather(
            self._fetch("metar", ids),
            self._fetch("taf", ids),
        )

        metar_map: dict[str, Any] = {}
        taf_map: dict[str, Any] = {}

        for m in metars:
            icao = _row_icao(m)
            if icao:
                metar_map[icao] = m

        for t in tafs:
            icao = _row_icao(t)
            if icao:
                taf_map[icao] = t

        _LOGGER.debug("AeroWeather got METAR=%s TAF=%s", list(metar_map), list(taf_map))

        return {"metar": metar_map, "taf": taf_map}
