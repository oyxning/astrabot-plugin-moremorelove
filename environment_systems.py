"""Utility subsystems for real-world time and weather support."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from urllib import parse, request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _current_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.get_event_loop()


class RealWorldTimeSystem:
    """Handles time-zone aware timestamps for the plugin."""

    def __init__(self, timezone: str = "Asia/Shanghai"):
        self._timezone_name = timezone
        self._tz = self._safe_zone_info(timezone)

    @staticmethod
    def _safe_zone_info(tz_name: str):
        if ZoneInfo is None:
            return None
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    def set_timezone(self, timezone: str):
        self._timezone_name = timezone
        self._tz = self._safe_zone_info(timezone)

    def get_summary(self) -> str:
        now = datetime.utcnow()
        if self._tz is not None:
            now = now.astimezone(self._tz)
        weekday = WEEKDAY_NAMES[now.weekday()]
        return f"{now:%Y-%m-%d %H:%M} {weekday} ({self._timezone_name})"


@dataclass
class WeatherInfo:
    location: str
    description: str
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    updated_at: datetime = datetime.utcnow()

    def brief(self) -> str:
        temp_part = ""
        if self.temperature_c is not None:
            temp_part = f" {self.temperature_c:.1f}°C"
            if self.feels_like_c is not None and abs(
                self.feels_like_c - self.temperature_c
            ) >= 1.5:
                temp_part += f" (体感 {self.feels_like_c:.1f}°C)"
        return f"{self.location}：{self.description}{temp_part}"


class RealWorldWeatherSystem:
    """Fetches weather data using the public wttr.in endpoint with caching."""

    def __init__(self, default_location: str = "", refresh_minutes: int = 60):
        self._default_location = default_location.strip()
        self._refresh = max(refresh_minutes, 10)
        self._cache: Dict[str, Tuple[datetime, WeatherInfo]] = {}

    def set_default_location(self, location: str):
        self._default_location = location.strip()

    def set_refresh_minutes(self, minutes: int):
        self._refresh = max(minutes, 10)

    async def get_weather(self, location: Optional[str] = None) -> WeatherInfo:
        loc = (location or self._default_location or "Shanghai").strip()
        cache_key = loc.lower()
        now = datetime.utcnow()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < timedelta(minutes=self._refresh):
            return cached[1]

        data = await self._fetch_weather(loc)
        info = self._parse_weather(loc, data)
        self._cache[cache_key] = (now, info)
        return info

    async def _fetch_weather(self, location: str) -> Optional[dict]:
        encoded = parse.quote(location or "Shanghai")
        url = f"https://wttr.in/{encoded}?format=j1"

        loop = _current_event_loop()

        def _do_fetch() -> Optional[dict]:
            try:
                with request.urlopen(url, timeout=8) as resp:
                    content = resp.read().decode("utf-8")
                    return json.loads(content)
            except Exception:
                return None

        return await loop.run_in_executor(None, _do_fetch)

    def _parse_weather(self, location: str, data: Optional[dict]) -> WeatherInfo:
        if not data:
            return WeatherInfo(location=location, description="天气信息获取失败")

        try:
            current = data["current_condition"][0]
            description = current["weatherDesc"][0]["value"]
            temp = float(current["temp_C"])
            feels_like = float(current["FeelsLikeC"])
            return WeatherInfo(
                location=location,
                description=description,
                temperature_c=temp,
                feels_like_c=feels_like,
            )
        except Exception:
            return WeatherInfo(location=location, description="天气数据解析失败")
