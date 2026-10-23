"""Pure NMEA 0183 sentence parsing and field mapping -> GpsFix.

No I/O: takes raw sentence strings (as read off the serial port by
serial_reader.py) through pynmea2 and maps the result onto this device's
canonical field names/units, matching hub/schema/gps.schema.json. Every
function here is pure and fixture-testable -- no serial hardware required
(prior art: driver-tank's calibration.py).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pynmea2

# GGA sentence field 6 (fix quality), per NMEA 0183.
_FIX_QUALITY = {
    0: "no_fix",
    1: "gps",
    2: "dgps",
    3: "pps",
    4: "rtk",
    5: "float_rtk",
    6: "estimated",
    7: "manual",
    8: "simulation",
}

_KNOTS_TO_KMH = 1.852

# GSV talker ID -> hub/schema/gps.schema.json's constellation enum. GN (multi-constellation
# talker) never appears on a GSV sentence; a receiver emits one GSV set per constellation.
# Anything not listed is "other" so a new talker never drops its satellites.
_CONSTELLATION = {
    "GP": "gps",
    "GL": "glonass",
    "GA": "galileo",
    "GB": "beidou",
    "BD": "beidou",
    "GQ": "qzss",
}


@dataclass(frozen=True)
class Satellite:
    """One satellite in view, from a GSV slot -- hub/schema/gps.schema.json's `satellites` item.

    snr_db/elevation_deg/azimuth_deg are None when the receiver leaves that GSV field blank
    (a satellite it knows of but is not yet measuring); never 0.
    """

    constellation: str
    prn: int
    snr_db: float | None
    elevation_deg: int | None
    azimuth_deg: int | None


@dataclass(frozen=True)
class GpsFix:
    """Combined position fix -- hub/schema/gps.schema.json's live field set.

    fix_quality/satellites_in_use are always present; every position/
    motion field is None until a fix is acquired (fix_quality !=
    "no_fix"). avg_snr_db is independent of fix_quality -- raw signal
    tracking is meaningful even before/without a fix -- so it survives a
    no_fix reset and is only ever cleared by a poll with no GSV data.
    """

    fix_quality: str = "no_fix"
    satellites_in_use: int = 0
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    hdop: float | None = None
    speed_kmh: float | None = None
    course_deg: float | None = None
    fix_time: str | None = None
    avg_snr_db: float | None = None
    satellites: tuple[Satellite, ...] | None = None


def parse_gga(line: str) -> pynmea2.types.talker.GGA | None:
    """Parse one NMEA line as a GGA sentence; None if it isn't one or fails to parse."""
    try:
        msg = pynmea2.parse(line)
    except pynmea2.ParseError:
        return None
    return msg if isinstance(msg, pynmea2.types.talker.GGA) else None


def parse_rmc(line: str) -> pynmea2.types.talker.RMC | None:
    """Parse one NMEA line as an RMC sentence; None if it isn't one or fails to parse."""
    try:
        msg = pynmea2.parse(line)
    except pynmea2.ParseError:
        return None
    return msg if isinstance(msg, pynmea2.types.talker.RMC) else None


def parse_gsv(line: str) -> pynmea2.types.talker.GSV | None:
    """Parse one NMEA line as a GSV sentence; None if it isn't one or fails to parse.

    GSV carries per-satellite signal data (elevation/azimuth/SNR), unlike
    GGA/RMC -- one talker ID per constellation (GPGSV/GLGSV/GAGSV/GBGSV),
    each needing possibly several sentences to list every tracked
    satellite. gsv_snr_values below extracts one sentence's readings;
    the caller accumulates across sentences/constellations before
    averaging via apply_gsv.
    """
    try:
        msg = pynmea2.parse(line)
    except pynmea2.ParseError:
        return None
    return msg if isinstance(msg, pynmea2.types.talker.GSV) else None


def gsv_snr_values(gsv: pynmea2.types.talker.GSV) -> list[float]:
    """This GSV sentence's up-to-4 per-satellite SNR readings (dB-Hz).

    Skips slots with no satellite (trailing slots in a set's last
    sentence) and satellites tracked but not yet strong enough to report
    an SNR value -- both come back as empty strings from pynmea2.
    """
    values: list[float] = []
    for i in (1, 2, 3, 4):
        prn = getattr(gsv, f"sv_prn_num_{i}")
        snr = getattr(gsv, f"snr_{i}")
        if prn and snr not in (None, ""):
            values.append(float(snr))
    return values


def _optional_number(raw: str | None, kind: type[int] | type[float]) -> int | float | None:
    """A GSV numeric field as `kind`, None when the receiver left it blank."""
    if raw in (None, ""):
        return None
    return kind(raw)


def gsv_satellites(gsv: pynmea2.types.talker.GSV) -> list[Satellite]:
    """This GSV sentence's up-to-4 satellites, every one the receiver lists.

    Unlike gsv_snr_values, a satellite with a blank SNR is kept (snr_db=None): it is in view,
    and a consumer shows "no signal yet" for it. Only empty slots (trailing slots of a set's
    last sentence, blank PRN) are skipped. A PRN that is not a positive integer is skipped,
    since the schema cannot represent it.
    """
    constellation = _CONSTELLATION.get(gsv.talker, "other")
    satellites: list[Satellite] = []
    for i in (1, 2, 3, 4):
        prn = getattr(gsv, f"sv_prn_num_{i}")
        if not prn or not prn.isdigit() or int(prn) < 1:
            continue
        satellites.append(
            Satellite(
                constellation=constellation,
                prn=int(prn),
                snr_db=_optional_number(getattr(gsv, f"snr_{i}"), float),
                elevation_deg=_optional_number(getattr(gsv, f"elevation_deg_{i}"), int),
                azimuth_deg=_optional_number(getattr(gsv, f"azimuth_{i}"), int),
            )
        )
    return satellites


def apply_gga(fix: GpsFix, gga: pynmea2.types.talker.GGA) -> GpsFix:
    """Fold a parsed GGA sentence's quality/satellite/HDOP/position/altitude fields onto `fix`.

    A fix_quality of "no_fix" drops any previously-held position fields
    (gga.latitude/longitude read as 0.0 when unfixed, which would otherwise
    look like a real fix at 0,0) but preserves avg_snr_db -- raw signal
    tracking is independent of fix status.
    """
    quality = _FIX_QUALITY.get(int(gga.gps_qual or 0), "no_fix")
    if quality == "no_fix":
        return GpsFix(
            fix_quality="no_fix",
            satellites_in_use=int(gga.num_sats or 0),
            avg_snr_db=fix.avg_snr_db,
            satellites=fix.satellites,
        )
    return replace(
        fix,
        fix_quality=quality,
        satellites_in_use=int(gga.num_sats or 0),
        latitude=gga.latitude,
        longitude=gga.longitude,
        altitude_m=float(gga.altitude) if gga.altitude is not None else None,
        hdop=float(gga.horizontal_dil) if gga.horizontal_dil else None,
    )


def apply_rmc(fix: GpsFix, rmc: pynmea2.types.talker.RMC) -> GpsFix:
    """Fold a parsed RMC sentence's speed/course/timestamp fields onto `fix`.

    Ignored if RMC reports void status ("V") or no GGA fix has been folded
    in yet -- RMC's own "A"/"V" status can disagree with GGA's fix_quality
    by a sentence or two during acquisition/loss; GGA stays the single
    source of truth for fix_quality.
    """
    if rmc.status != "A" or fix.fix_quality == "no_fix":
        return fix
    fix_time = None
    if rmc.datestamp is not None and rmc.timestamp is not None:
        fix_time = datetime.combine(rmc.datestamp, rmc.timestamp, tzinfo=UTC).isoformat()
    return replace(
        fix,
        speed_kmh=(
            float(rmc.spd_over_grnd) * _KNOTS_TO_KMH if rmc.spd_over_grnd is not None else None
        ),
        course_deg=float(rmc.true_course) if rmc.true_course is not None else None,
        fix_time=fix_time,
    )


def apply_gsv(fix: GpsFix, snr_values: list[float]) -> GpsFix:
    """Fold a batch of SNR readings (one or more GSV sentences, any
    constellation, accumulated by the caller across a poll window) onto
    `fix` as their mean -- independent of fix_quality, since raw signal
    tracking is meaningful even before/without a fix.

    A poll with no GSV data leaves avg_snr_db unchanged (stale, not
    cleared) -- consistent with the rest of GpsFix's "republish the last
    known state" behavior (see serial_reader.py's SerialReader docstring).
    """
    if not snr_values:
        return fix
    return replace(fix, avg_snr_db=round(sum(snr_values) / len(snr_values), 1))


def apply_satellites(fix: GpsFix, satellites: list[Satellite], saw_gsv: bool) -> GpsFix:
    """Fold the satellites seen in one poll window onto `fix`, independent of fix_quality.

    `satellites` is every GSV slot of the window, any constellation; `saw_gsv` is whether the
    window carried any GSV sentence at all. The receiver repeats each constellation's whole GSV
    set about once a second, so a window holds several copies of the same satellite: the last
    one wins, keyed by (constellation, prn). A satellite absent from the window drops out, so a
    set satellite leaves the array.

    A window with no GSV sentence leaves `satellites` unchanged (stale, not cleared), the same
    rule as avg_snr_db. A window with GSV but no satellites (`$GPGSV,1,1,00`: the receiver
    reports nothing in view) sets the empty tuple, which is published as `[]`.
    """
    if not saw_gsv:
        return fix
    latest = {(sat.constellation, sat.prn): sat for sat in satellites}
    ordered = sorted(latest.values(), key=lambda sat: (sat.constellation, sat.prn))
    return replace(fix, satellites=tuple(ordered))
