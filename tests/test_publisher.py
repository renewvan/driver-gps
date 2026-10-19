"""Behavioural tests for Publisher's connect/disconnect bus traffic.

Seam: Publisher with paho's Client replaced by a recording fake -- asserts
what reaches the bus, in order, not how Publisher is built internally.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from node_gps import publisher as publisher_module
from node_gps.config import MqttConfig
from node_gps.publisher import HEALTH_TOPIC, INFO_TOPIC, Publisher

_INFO = '{"node": "gps", "version": "v1.2.3"}'


@dataclass
class _Published:
    topic: str
    payload: str
    qos: int
    retain: bool


@dataclass
class _FakeClient:
    published: list[_Published] = field(default_factory=list)
    will: _Published | None = None
    on_connect: object = None
    on_disconnect: object = None
    on_message: object = None

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.published = []
        self.will = None

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
def publisher(monkeypatch: pytest.MonkeyPatch) -> Publisher:
    monkeypatch.setattr(publisher_module.mqtt, "Client", _FakeClient)
    config = MqttConfig(
        host="localhost",
        port=1883,
        username=None,
        password=None,
        client_id="node-gps-test",
        reconnect_min_delay=1.0,
        reconnect_max_delay=30.0,
    )
    return Publisher(config, info_payload=_INFO)


def _connect(publisher: Publisher) -> _FakeClient:
    client = publisher._client
    client.on_connect(client, None, {}, 0)
    return client


def test_info_is_published_retained_immediately_before_online(publisher: Publisher) -> None:
    client = _connect(publisher)

    assert client.published == [
        _Published(INFO_TOPIC, _INFO, qos=1, retain=True),
        _Published(HEALTH_TOPIC, "online", qos=1, retain=True),
    ]


def test_info_is_published_again_on_reconnect(publisher: Publisher) -> None:
    client = _connect(publisher)
    client.published.clear()

    client.on_connect(client, None, {}, 0)

    assert [p.topic for p in client.published] == [INFO_TOPIC, HEALTH_TOPIC]


def test_failed_connect_publishes_nothing(publisher: Publisher) -> None:
    client = publisher._client

    client.on_connect(client, None, {}, 5)

    assert client.published == []


def test_clean_shutdown_flips_health_but_does_not_clear_info(publisher: Publisher) -> None:
    client = _connect(publisher)
    client.published.clear()

    publisher.disconnect()

    assert client.published == [_Published(HEALTH_TOPIC, "offline", qos=1, retain=True)]


def test_last_will_flips_health_only(publisher: Publisher) -> None:
    assert publisher._client.will == _Published(HEALTH_TOPIC, "offline", qos=1, retain=True)
