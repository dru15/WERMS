"""Bounded, cached model weather context. Never used as a fire-risk score."""

import json
import math
import threading
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIELDS = {
    "temperature_2m": ("temperature_c", "°C", -90, 65),
    "relative_humidity_2m": ("humidity_pct", "%", 0, 100),
    "wind_speed_10m": ("wind_kph", "km/h", 0, 500),
    "wind_direction_10m": ("wind_direction_degrees", "°", 0, 360),
    "precipitation": ("precipitation_mm", "mm", 0, 1000),
}


def fetch_weather(latitude: float, longitude: float, api_key: str | None = None) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(FIELDS),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timeformat": "unixtime",
        "timezone": "Asia/Kolkata",
        "forecast_days": 1,
    }
    endpoint = "https://api.open-meteo.com/v1/forecast"
    if api_key:
        endpoint = "https://customer-api.open-meteo.com/v1/forecast"
        params["apikey"] = api_key
    request = Request(f"{endpoint}?{urlencode(params)}", headers={"User-Agent": "WERMS/0.5"})
    with urlopen(request, timeout=6) as response:
        payload = response.read(100_001)
    if len(payload) > 100_000:
        raise ValueError("Weather response exceeds limit.")
    return json.loads(payload)


def validate_weather(raw: dict, now: datetime, latitude: float, longitude: float) -> dict:
    current, units = raw["current"], raw["current_units"]
    if units["time"] != "unixtime" or units["interval"] != "seconds":
        raise ValueError("Unexpected weather time units.")
    valid = datetime.fromtimestamp(current["time"], UTC)
    if valid > now + timedelta(minutes=10) or now - valid > timedelta(minutes=90):
        raise ValueError("Weather validity time is outside the accepted window.")
    interval = current["interval"]
    if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 3600:
        raise ValueError("Weather aggregation interval is invalid.")
    if (
        any(not math.isfinite(float(raw[k])) for k in ("latitude", "longitude"))
        or abs(float(raw["latitude"]) - latitude) > 0.5
        or abs(float(raw["longitude"]) - longitude) > 0.5
    ):
        raise ValueError("Weather grid is outside the pilot region.")
    result = {}
    for field, (name, unit, minimum, maximum) in FIELDS.items():
        value = current[field]
        if (
            units[field] != unit
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise ValueError("Weather field or unit is invalid.")
        result[name] = value
    return {
        **result,
        "valid_at": valid.isoformat(),
        "interval_seconds": interval,
        "retrieved_at": now.isoformat(),
        "grid_latitude": raw["latitude"],
        "grid_longitude": raw["longitude"],
    }


class WeatherContext:
    def __init__(
        self,
        network: dict,
        *,
        enabled: bool = True,
        api_key: str | None = None,
        fetch=fetch_weather,
    ):
        self.enabled = enabled and network.get("country") == "IN"
        bounds = network.get("bounds", [0, 0, 0, 0])
        self.latitude, self.longitude = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        self.fetch, self.api_key = fetch, api_key
        self._lock = threading.Lock()
        self._data = None
        self._next_attempt = datetime.min.replace(tzinfo=UTC)
        self._error = None

    def snapshot(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        base = {
            "provider": "Open-Meteo",
            "source_url": "https://open-meteo.com/",
            "data_kind": "model-derived-current-weather",
            "timezone": "Asia/Kolkata",
            "affects_routing": False,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        if not self.enabled:
            return {
                **base,
                "status": "disabled",
                "data": None,
                "message": "Weather context is disabled.",
            }
        # One provider request at a time, including concurrent browser polls.
        with self._lock:
            if now >= self._next_attempt:
                try:
                    self._data = validate_weather(
                        self.fetch(self.latitude, self.longitude, self.api_key),
                        now,
                        self.latitude,
                        self.longitude,
                    )
                    self._next_attempt = now + timedelta(minutes=10)
                    self._error = None
                except (OSError, ValueError, KeyError, TypeError, OverflowError):
                    self._next_attempt = now + timedelta(minutes=1)
                    self._error = (
                        "Provider unavailable or response rejected. "
                        "No replacement reading was invented."
                    )
            data = self._data
            if data and now - datetime.fromisoformat(data["retrieved_at"]) > timedelta(hours=3):
                data = None
            stale = data and (
                self._error
                or now - datetime.fromisoformat(data["valid_at"]) > timedelta(minutes=60)
            )
            return {
                **base,
                "status": "unavailable" if data is None else "stale" if stale else "current",
                "data": data,
                "message": self._error,
            }
