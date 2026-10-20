from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from werms_api.weather import WeatherContext, validate_weather

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
NETWORK = {"country": "IN", "bounds": [30.3, 78.0, 30.4, 78.1]}


def payload():
    return {
        "latitude": 30.35,
        "longitude": 78.05,
        "current_units": {
            "time": "unixtime",
            "interval": "seconds",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
            "wind_direction_10m": "°",
            "precipitation": "mm",
        },
        "current": {
            "time": int(NOW.timestamp()),
            "interval": 900,
            "temperature_2m": 24,
            "relative_humidity_2m": 40,
            "wind_speed_10m": 13,
            "wind_direction_10m": 90,
            "precipitation": 0,
        },
    }


def test_concurrent_weather_reads_share_one_request_and_do_not_influence_routes():
    calls = []

    def fetch(*_):
        calls.append(True)
        return payload()

    service = WeatherContext(NETWORK, fetch=fetch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.snapshot(now=NOW), range(8)))
    assert len(calls) == 1
    assert all(r["status"] == "current" and r["affects_routing"] is False for r in results)
    assert results[0]["data"]["valid_at"] == NOW.isoformat()


def test_cached_weather_is_marked_stale_after_failure_and_discarded_after_three_hours():
    calls = []

    def fetch(*_):
        if calls:
            raise OSError("provider offline")
        calls.append(True)
        return payload()

    service = WeatherContext(NETWORK, fetch=fetch)
    assert service.snapshot(now=NOW)["status"] == "current"
    stale = service.snapshot(now=NOW + timedelta(minutes=11))
    assert stale["status"] == "stale" and stale["data"]["temperature_c"] == 24
    assert service.snapshot(now=NOW + timedelta(hours=4))["status"] == "unavailable"
    assert WeatherContext(NETWORK, enabled=False).snapshot()["status"] == "disabled"


@pytest.mark.parametrize(
    "field,value",
    [
        ("temperature_2m", None),
        ("wind_speed_10m", float("nan")),
        ("relative_humidity_2m", 101),
        ("interval", 0),
        ("time", int((NOW + timedelta(hours=1)).timestamp())),
    ],
)
def test_invalid_weather_fields_are_rejected(field, value):
    raw = payload()
    raw["current"][field] = value
    with pytest.raises((ValueError, TypeError)):
        validate_weather(raw, NOW, 30.35, 78.05)


def test_wrong_units_are_rejected_instead_of_silently_converted():
    raw = payload()
    raw["current_units"]["wind_speed_10m"] = "m/s"
    with pytest.raises(ValueError):
        validate_weather(raw, NOW, 30.35, 78.05)
