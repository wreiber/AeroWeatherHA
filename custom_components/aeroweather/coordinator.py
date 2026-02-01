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
BASE = "https://aviationweather.gov/api/data"  # Data API base :contentReference[oaicite:1]{index=1}


async def _fetch_json(session: ClientSession, endpoint: str, params: dict[str, Any]) -> Any:
    url = f"{BASE}/{endpoint}"
    async with session.get(url, params=params, timeout=20) as resp:
        resp.raise_for_status()
        return await resp.json()


def _row_icao(row: dict[str, Any]) -> str | None:
    # API payloads sometimes vary; be defensive.
    icao = row.get("icaoId") or row.get("station") or row.get("id") or row.get("icao")
    if not icao:
        return None
    return str(icao).upper().strip()


class AeroWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.session = async_get_clientsession(hass)

        data = {**entry.data, **(entry.options or {})}

        # IMPORTANT: normalize ICAOs to uppercase to match keys we store and what sensors use
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

    async def _async_update(self) -> dict[str, Any]:
        if not self.icaos:
            return {"metar": {}, "taf": {}}

        params = {"ids": ",".join(self.icaos), "format": "json"}

        try:
            metars, tafs = await asyncio.gather(
                _fetch_json(self.session, "metar", params),
                _fetch_json(self.session, "taf", params),
            )
        except (ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"AeroWeather fetch failed: {err}") from err

        metar_map: dict[str, Any] = {}
        taf_map: dict[str, Any] = {}

        for row in metars or []:
            if isinstance(row, dict):
                icao = _row_icao(row)
                if icao:
                    metar_map[icao] = row

        for row in tafs or []:
            if isinstance(row, dict):
                icao = _row_icao(row)
                if icao:
                    taf_map[icao] = row

        _LOGGER.debug("AeroWeather stations metar=%s taf=%s", list(metar_map), list(taf_map))

        return {"metar": metar_map, "taf": taf_map}

async def _fetch(self, endpoint: str, ids: str):
    async with self.session.get(
        f"{API_BASE}/{endpoint}",
        params={"ids": ids, "format": "json"},
        timeout=20,
    ) as resp:
        # No content = no TAF/METAR available (common for TAF). Not an error.
        if resp.status == 204:
            return []

        if resp.status != 200:
            text = await resp.text()
            raise UpdateFailed(f"{endpoint} HTTP {resp.status}: {text[:200]}")

        payload = await resp.json(content_type=None)

        # Normalize list vs wrapped dict responses
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "results", endpoint):
                val = payload.get(key)
                if isinstance(val, list):
                    return val
        return []


        ids = ",".join(self.icaos)
        try:
            metars, tafs = await asyncio.gather(
                self._fetch("metar", ids),
                self._fetch("taf", ids),
            )
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        return {
            "icaos": self.icaos,
            "metar": {
                (m.get("icaoId") or m.get("stationId")).upper(): m
                for m in metars or []
                if m.get("icaoId") or m.get("stationId")
            },
            "taf": {
                (t.get("icaoId") or t.get("stationId")).upper(): t
                for t in tafs or []
                if t.get("icaoId") or t.get("stationId")
            },
        }

