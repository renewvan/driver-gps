"""Behavioural tests for the published Device info payload.

Seam: build_info_payload() -- manifest + environment + /proc/cpuinfo in,
retained-info JSON out. No MQTT broker or hardware required.
"""

import json
from pathlib import Path

from driver_gps.device_info import build_info_payload


def _info(env: dict[str, str], cpuinfo: Path | None = None) -> dict:
    return json.loads(
        build_info_payload(env=env, cpuinfo_path=cpuinfo or Path("/nonexistent/cpuinfo"))
    )


def test_info_identifies_the_gps_device_and_what_it_publishes() -> None:
    info = _info({})

    assert info["device"] == "gps"
    assert info["publishes"] == ["gps"]
    assert info["product"]
    assert info["source"]


def test_info_carries_the_stamped_version() -> None:
    assert _info({"DEVICE_VERSION": "v1.2.3"})["version"] == "v1.2.3"


def test_info_version_is_dev_when_unset() -> None:
    assert _info({})["version"] == "dev"


def test_info_version_is_dev_when_blank() -> None:
    assert _info({"DEVICE_VERSION": ""})["version"] == "dev"


def _cpuinfo(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cpuinfo"
    path.write_text(text)
    return path


_PI_CPUINFO = """\
processor\t: 0
model name\t: ARMv7 Processor rev 3 (v7l)
BogoMIPS\t: 108.00

Hardware\t: BCM2711
Revision\t: c03111
Serial\t\t: 10000000a1b2c3d4
Model\t\t: Raspberry Pi 4 Model B Rev 1.1
"""


def test_info_board_serial_comes_from_cpuinfo_serial_line(tmp_path: Path) -> None:
    info = _info({}, _cpuinfo(tmp_path, _PI_CPUINFO))

    assert info["board_serial"] == "10000000a1b2c3d4"


def test_info_omits_board_serial_when_cpuinfo_unreadable(tmp_path: Path) -> None:
    info = _info({}, tmp_path / "does-not-exist")

    assert "board_serial" not in info


def test_info_omits_board_serial_when_serial_line_missing(tmp_path: Path) -> None:
    info = _info({}, _cpuinfo(tmp_path, "processor\t: 0\nmodel name\t: x86\n"))

    assert "board_serial" not in info


def test_info_omits_board_serial_when_serial_empty(tmp_path: Path) -> None:
    info = _info({}, _cpuinfo(tmp_path, "Serial\t\t: \n"))

    assert "board_serial" not in info


def test_info_omits_board_serial_when_serial_all_zeros(tmp_path: Path) -> None:
    info = _info({}, _cpuinfo(tmp_path, "Serial\t\t: 0000000000000000\n"))

    assert "board_serial" not in info
