"""What read_and_publish puts on the bus for the `satellites` property.

A stub reader and publisher stand in for the serial port and the broker; the assertions are on
the topic and the exact JSON payload a consumer receives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from driver_gps.config import AppConfig, DeviceConfig, MqttConfig
from driver_gps.driver import read_and_publish
from driver_gps.nmea import GpsFix, Satellite

_TOPIC = "renewvan/gps/gps/satellites"


@dataclass
class _Reader:
    fix: GpsFix

    def read_fix(self, timeout_s: float) -> GpsFix:
        return self.fix


@dataclass
class _Publisher:
    sent: dict[str, str] = field(default_factory=dict)

    def publish(self, topic: str, payload: str) -> None:
        self.sent[topic] = payload


_CONFIG = AppConfig(
    mqtt=MqttConfig("localhost", 1883, None, None, "driver-gps", 1.0, 30.0),
    device=DeviceConfig("gps", 3000, "/dev/null", 9600, 2.0),
)


def _publish(fix: GpsFix) -> dict[str, str]:
    publisher = _Publisher()
    read_and_publish(publisher, _Reader(fix), _CONFIG)  # type: ignore[arg-type]
    return publisher.sent


def test_satellites_are_published_as_the_schema_item_shape_with_null_for_no_measurement() -> None:
    sent = _publish(
        GpsFix(
            satellites=(
                Satellite("gps", 10, 38.0, 45, 110),
                Satellite("beidou", 9, None, None, None),
            )
        )
    )
    assert json.loads(sent[_TOPIC]) == [
        {
            "constellation": "gps",
            "prn": 10,
            "snr_db": 38.0,
            "elevation_deg": 45,
            "azimuth_deg": 110,
        },
        {
            "constellation": "beidou",
            "prn": 9,
            "snr_db": None,
            "elevation_deg": None,
            "azimuth_deg": None,
        },
    ]


def test_satellites_are_published_without_a_fix() -> None:
    sent = _publish(GpsFix(fix_quality="no_fix", satellites=(Satellite("gps", 7, 18.0, 12, 301),)))
    assert len(json.loads(sent[_TOPIC])) == 1
    assert "renewvan/gps/gps/latitude" not in sent


def test_an_empty_sky_is_published_as_an_empty_array() -> None:
    assert json.loads(_publish(GpsFix(satellites=()))[_TOPIC]) == []


def test_nothing_is_published_for_satellites_before_the_first_gsv() -> None:
    assert _TOPIC not in _publish(GpsFix(satellites=None))
