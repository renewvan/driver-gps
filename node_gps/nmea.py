"""Pure NMEA 0183 sentence parsing and field mapping -> GpsFix.

No I/O: takes raw sentence strings (as read off the serial port by
serial_reader.py) through pynmea2 and maps the result onto this node's
canonical field names/units, matching hub/schema/gps.schema.json. Every
function here is pure and fixture-testable -- no serial hardware required
(prior art: node-tank's calibration.py).
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


@dataclass(frozen=True)
class GpsFix:
    """Combined position fix -- hub/schema/gps.schema.json's live field set.

    fix_quality/satellites_in_use are always present; every other field is
    None until a fix is acquired (fix_quality != "no_fix").
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


def apply_gga(fix: GpsFix, gga: pynmea2.types.talker.GGA) -> GpsFix:
    """Fold a parsed GGA sentence's quality/satellite/HDOP/position/altitude fields onto `fix`.

    A fix_quality of "no_fix" drops any previously-held position fields
    (gga.latitude/longitude read as 0.0 when unfixed, which would otherwise
    look like a real fix at 0,0).
    """
    quality = _FIX_QUALITY.get(int(gga.gps_qual or 0), "no_fix")
    if quality == "no_fix":
        return GpsFix(fix_quality="no_fix", satellites_in_use=int(gga.num_sats or 0))
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
        fix_time = datetime.combine(
            rmc.datestamp, rmc.timestamp, tzinfo=UTC
        ).isoformat()
    return replace(
        fix,
        speed_kmh=(
            float(rmc.spd_over_grnd) * _KNOTS_TO_KMH if rmc.spd_over_grnd is not None else None
        ),
        course_deg=float(rmc.true_course) if rmc.true_course is not None else None,
        fix_time=fix_time,
    )
