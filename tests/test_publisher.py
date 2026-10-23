"""Behavioural tests for Publisher's connect/disconnect bus traffic.

Seam: Publisher with paho's Client replaced by a recording fake -- asserts
what reaches the bus, in order, not how Publisher is built internally.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from driver_gps import publisher as publisher_module
from driver_gps.config import MqttConfig
from driver_gps.publisher import HEALTH_TOPIC, INFO_TOPIC, Publisher

_INFO = '{"driver": "gps", "version": "v1.2.3"}'


@dataclass
class _Published:
    topic: str
    payload: str
    qos: int
    retain: bool


class _FakeClient:
    """Records what reaches the bus; stands in for paho's mqtt.Client."""

    def __init__(self) -> None:
        self.published: list[_Published] = []
        self.will: _Published | None = None
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def username_pw_set(self, *args) -> None:  # noqa: ANN002
        pass

    def will_set(self, topic, payload, qos, retain) -> None:  # noqa: ANN001
        self.will = _Published(topic, payload, qos, retain)

    def reconnect_delay_set(self, **kwargs) -> None:  # noqa: ANN003
        pass

    def publish(self, topic, payload, qos, retain) -> None:  # noqa: ANN001
        self.published.append(_Published(topic, payload, qos, retain))

    def subscribe(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    def loop_stop(self) -> None:
        pass

    def disconnect(self) -> None:
        pass


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(publisher_module.mqtt, "Client", lambda **_: client)
    return client


@pytest.fixture
def publisher(fake: _FakeClient) -> Publisher:
    config = MqttConfig(
        host="localhost",
        port=1883,
        username=None,
        password=None,
        client_id="driver-gps-test",
        reconnect_min_delay=1.0,
        reconnect_max_delay=30.0,
    )
    return Publisher(config, info_payload=_INFO)


def _connect(fake: _FakeClient, rc: int = 0) -> None:
    """Simulate the broker accepting (rc=0) or refusing the connection."""
    fake.on_connect(fake, None, {}, rc)


def test_info_is_published_retained_immediately_before_online(
    publisher: Publisher, fake: _FakeClient
) -> None:
    _connect(fake)

    assert fake.published == [
        _Published(INFO_TOPIC, _INFO, qos=1, retain=True),
        _Published(HEALTH_TOPIC, "online", qos=1, retain=True),
    ]


def test_info_is_published_again_on_reconnect(publisher: Publisher, fake: _FakeClient) -> None:
    _connect(fake)
    fake.published.clear()

    _connect(fake)

    assert fake.published == [
        _Published(INFO_TOPIC, _INFO, qos=1, retain=True),
        _Published(HEALTH_TOPIC, "online", qos=1, retain=True),
    ]


def test_failed_connect_publishes_nothing(publisher: Publisher, fake: _FakeClient) -> None:
    _connect(fake, rc=5)

    assert fake.published == []


def test_clean_shutdown_flips_health_but_does_not_clear_info(
    publisher: Publisher, fake: _FakeClient
) -> None:
    _connect(fake)
    fake.published.clear()

    publisher.disconnect()

    assert fake.published == [_Published(HEALTH_TOPIC, "offline", qos=1, retain=True)]


def test_last_will_flips_health_only(publisher: Publisher, fake: _FakeClient) -> None:
    assert fake.will == _Published(HEALTH_TOPIC, "offline", qos=1, retain=True)
