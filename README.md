# node-gps

USB GPS module node (GLONASS/BeiDou/GPS) for renewvan position telemetry

Scaffolded from `renewvan/node-tank`'s reference shape via `renewvan/skills`'
`scaffold-node` skill (per the **Node** term in `hub/docs/architecture.md`'s
Terminology section: "anything that publishes one specific device or feed
onto the renewvan bus, normalized into the device model"). Layout: pure,
unit-testable conversion math with no I/O, a layered
`config.default.ini`/`config.ini` loader (`config.py`), a persistent MQTT
publisher with LWT (`publisher.py`), a thin publish loop (`driver.py`), a
systemd unit, and its own Dockerfile + CI publishing a versioned image.

**This node owns the sensing**: it reads a USB GPS/GLONASS/BeiDou module
directly over its serial port (NMEA 0183 sentences, no vendor cloud/MQTT
feed to remap), parses with `pynmea2`, and publishes via `pyserial`.

## Topics published

Retained, under `renewvan/gps/<id>/`:

Every field is **live** (republished on every poll, default 3s) — there
are no identity/startup-only fields. Position tracking has no meaningful
"publish once" subset; downstream logging (the `logger` repo) is what
turns this live stream into a trip history, not this node.

- `fix_quality` — `no_fix` / `gps` / `dgps` / `pps` / `rtk` / `float_rtk` / `estimated` / `manual` / `simulation` (GGA sentence's fix-quality field); unconditional
- `satellites_in_use` — integer ≥0 (GGA); unconditional, 0 when `fix_quality` is `no_fix`
- `avg_snr_db` — number ≥0, mean signal strength (C/N0, dB-Hz) across every tracked satellite with a decoded SNR (GSV sentences, any constellation); independent of `fix_quality` — meaningful even before/without a fix. Absent only before the first GSV sentence is decoded.
- `latitude` — number, decimal degrees WGS84, positive north; present only when `fix_quality != no_fix`
- `longitude` — number, decimal degrees WGS84, positive east; present only when `fix_quality != no_fix`
- `altitude_m` — number, meters above MSL (GGA); present only when `fix_quality != no_fix`
- `hdop` — number ≥0, horizontal dilution of precision (GGA); present only when `fix_quality != no_fix`
- `speed_kmh` — number ≥0, ground speed converted from RMC's knots (×1.852); present only when `fix_quality != no_fix`
- `course_deg` — number 0–360, track made good, degrees true (RMC); present only when `fix_quality != no_fix`
- `fix_time` — string, ISO-8601 UTC timestamp with explicit `+00:00` offset (RMC date+time — the GPS clock is always UTC); present only when `fix_quality != no_fix`

**Node liveness** (not GPS-keyed):
- `renewvan/gps/health` — `online`/`offline` via MQTT LWT
- `renewvan/gps/info` — retained Node info (see below)

Payload shapes match `hub`'s `schema/gps.schema.json`.

## Node info

On every MQTT connect the node publishes retained JSON to
`renewvan/gps/info`, **immediately before** `online` on
`renewvan/gps/health`. Info stays retained when the node goes offline or its
last will fires, so a consumer can show "offline, last seen vX".

The payload is `manifest.json` (repo root) plus two runtime fields:

- **Manifest** — `node`, `product`, `source`, `publishes`, optional
  `manufacturer`/`homepage`. It is the only hand-edited part. It must **not**
  contain `version` or `host_serial`; CI validates it against the hub's
  `node-manifest.schema.json` at the hub ref pinned in
  `.github/workflows/test.yml` (`scripts/validate-manifest.sh`). The Docker
  image copies it to `node_gps/manifest.json`; the node reads that copy beside
  its module and falls back to the repo-root file in a checkout.
- **`version`** — the git release tag, and nothing else. The release workflow
  passes it as the `NODE_VERSION` build argument, which the Dockerfile exposes
  as an environment variable. When it is unset or empty (a checkout or
  untagged image) the node reports the literal `dev`. There is no `version`
  file or `__version__`, and `pyproject.toml`'s `0.0.0` is a placeholder that
  nothing reads.
- **`host_serial`** — the `Serial` line of the host's `/proc/cpuinfo`, read once
  at start (a default container can read it; no mount needed). Omitted when
  the file is unreadable or the serial is empty or all zeros.

`node_gps/node_info.py` is deliberately copied into each node repo rather than
shared as a package (`renewvan/hub#35`).

## Wiring

Plug the USB GPS module into the Pi. It's a USB-serial device (no I2C/GPIO
wiring) — the only setup is finding its device path and granting the
runtime user permission to open it:

1. **Find the serial device**: `dmesg | tail` right after plugging in.
   u-blox-native USB (CDC-ACM) chips usually enumerate as `/dev/ttyACM0`;
   CP2102/CH340 USB-serial bridge clones (common on cheap "U-8 chip"
   GLONASS/BeiDou/GPS dongles) usually enumerate as `/dev/ttyUSB0`.
2. **Set `serial_port`** in `config.ini` to that path (see
   `config.ini.example`). `baud_rate` defaults to `9600`, the near-universal
   NMEA factory default for these modules.
3. **Grant serial access**: add the runtime user to the `dialout` group
   (`sudo usermod -aG dialout <user>`) — `node-gps.service` already sets
   `SupplementaryGroups=dialout`. No group membership means a permission
   error opening the port, not a crash on missing hardware.
4. **Multiple USB-serial devices on the same Pi?** `/dev/ttyUSB0` isn't
   stable across reboots/replugs if there's more than one. Pin a udev rule
   by vendor/product ID (`udevadm info -a -n /dev/ttyUSB0`) to a symlink
   like `/dev/gps0`, and point `serial_port` at that instead.

## Development

```bash
git clone git@github.com:renewvan/node-gps.git
cd node-gps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
```

Keep conversion/decision logic in pure functions tested against fixture
values — no MQTT broker or real hardware required for any of it. Before
opening a PR: `pytest tests/ -v` must pass (same command CI runs), and any
change to a published field needs a matching
`hub/schema/gps.schema.json` update in a `hub` PR (per
`hub/docs/adr/0001-compose-services-via-pinned-images-not-git-submodules.md`,
the two repos are never coupled at build time, only at the schema-version
level).

## Configuration

`config.default.ini` ships every key with a default. Copy
`config.ini.example` to `config.ini` (gitignored) and override only what
differs.

## Running

```bash
pip install -r requirements.txt
python -m node_gps.main --config config.ini
```

Install `node_gps/systemd/node-gps.service` to run at boot
(`Restart=on-failure`).

## Testing

```bash
pip install -r requirements.txt -r requirements-test.txt
pytest tests/ -v
```

## Releasing

Tagging a GitHub release builds and publishes
`ghcr.io/<owner>/node-gps:<tag>`, which `hub`'s deployment compose file pins
by tag (never builds from source — see
`hub/docs/adr/0001-compose-services-via-pinned-images-not-git-submodules.md`).

The release tag is also stamped into the image as `NODE_VERSION` (see
[Node info](#node-info)), so the version a node publishes always equals its
image tag.
