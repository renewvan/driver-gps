"""The CI manifest gate: scripts/validate-manifest.sh against a schema.

The real schema lives in renewvan/hub and is fetched by CI at a pinned ref.
These tests use a minimal schema with the same contract (draft-07,
additionalProperties false, no `version`/`board_serial` property) so the
gate's pass/fail behaviour is proven without network access to the hub.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from driver_gps.publisher import INFO_TOPIC

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE = _REPO_ROOT / "scripts" / "validate-manifest.sh"
_MANIFEST = _REPO_ROOT / "manifest.json"

_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["device", "product", "source", "publishes"],
    "additionalProperties": False,
    "properties": {
        "device": {"type": "string"},
        "product": {"type": "string"},
        "source": {"type": "string"},
        "publishes": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "manufacturer": {"type": "string"},
        "homepage": {"type": "string"},
    },
}


def _ajv_available() -> bool:
    """True when ajv-cli can actually run (npx present and the package resolvable).

    Without this, the negative tests (`returncode != 0`) would pass for the wrong reason
    on a machine where ajv cannot start.
    """
    if shutil.which("npx") is None:
        return False
    probe = subprocess.run(
        ["npx", "--yes", "ajv-cli@5", "help"], capture_output=True, text=True, timeout=120
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _ajv_available(), reason="ajv-cli@5 not runnable via npx")


def _gate(tmp_path: Path, manifest: dict) -> subprocess.CompletedProcess:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(_SCHEMA))
    candidate = tmp_path / "manifest.json"
    candidate.write_text(json.dumps(manifest))
    return subprocess.run([str(_GATE), str(schema), str(candidate)], capture_output=True, text=True)


def test_gate_passes_on_the_real_manifest(tmp_path: Path) -> None:
    result = _gate(tmp_path, json.loads(_MANIFEST.read_text()))

    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_fails_on_a_manifest_containing_version(tmp_path: Path) -> None:
    manifest = json.loads(_MANIFEST.read_text()) | {"version": "v1.0.0"}

    result = _gate(tmp_path, manifest)

    assert result.returncode != 0


def test_gate_fails_on_a_manifest_containing_board_serial(tmp_path: Path) -> None:
    manifest = json.loads(_MANIFEST.read_text()) | {"board_serial": "10000000a1b2c3d4"}

    result = _gate(tmp_path, manifest)

    assert result.returncode != 0


def test_info_topic_uses_the_manifest_device_key() -> None:
    device = json.loads(_MANIFEST.read_text())["device"]

    assert INFO_TOPIC == f"renewvan/{device}/info"
