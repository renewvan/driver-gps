"""Fixture-sentence tests for nmea.py's pure parse/apply functions -- no
serial hardware or MQTT broker required.

Prior art: node-tank's tests/test_calibration.py (fixture input, pure
function, no I/O).
"""

from node_gps.nmea import GpsFix, apply_gga, apply_rmc, parse_gga, parse_rmc

_GGA_FIX = "$GPGGA,123456.00,4527.852,N,00911.400,E,1,08,0.9,122.3,M,45.9,M,,*66"
_GGA_NO_FIX = "$GPGGA,123456.00,,,,,0,00,99.99,,M,,M,,*61"
_RMC_ACTIVE = "$GPRMC,123456.00,A,4527.852,N,00911.400,E,33.7,184.7,041026,,,A*63"
_RMC_VOID = "$GPRMC,123456.00,V,,,,,,,,,,N*7A"


def test_parse_gga_rejects_non_gga_sentence() -> None:
    assert parse_gga(_RMC_ACTIVE) is None


def test_parse_rmc_rejects_non_rmc_sentence() -> None:
    assert parse_rmc(_GGA_FIX) is None


def test_parse_gga_rejects_garbage() -> None:
    assert parse_gga("not a sentence") is None


def test_apply_gga_with_fix_sets_position_and_quality() -> None:
    gga = parse_gga(_GGA_FIX)
    assert gga is not None
    fix = apply_gga(GpsFix(), gga)
    assert fix.fix_quality == "gps"
    assert fix.satellites_in_use == 8
    assert fix.latitude == gga.latitude
    assert fix.longitude == gga.longitude
    assert fix.altitude_m == 122.3
    assert fix.hdop == 0.9


def test_apply_gga_no_fix_clears_any_prior_position() -> None:
    gga = parse_gga(_GGA_FIX)
    no_fix_gga = parse_gga(_GGA_NO_FIX)
    assert gga is not None and no_fix_gga is not None
    had_fix = apply_gga(GpsFix(), gga)
    cleared = apply_gga(had_fix, no_fix_gga)
    assert cleared == GpsFix(fix_quality="no_fix", satellites_in_use=0)


def test_apply_rmc_adds_speed_course_and_utc_fix_time() -> None:
    gga = parse_gga(_GGA_FIX)
    rmc = parse_rmc(_RMC_ACTIVE)
    assert gga is not None and rmc is not None
    fix = apply_rmc(apply_gga(GpsFix(), gga), rmc)
    assert fix.speed_kmh == 33.7 * 1.852
    assert fix.course_deg == 184.7
    assert fix.fix_time == "2026-10-04T12:34:56+00:00"


def test_apply_rmc_void_status_is_ignored() -> None:
    gga = parse_gga(_GGA_FIX)
    rmc_void = parse_rmc(_RMC_VOID)
    assert gga is not None and rmc_void is not None
    had_fix = apply_gga(GpsFix(), gga)
    unchanged = apply_rmc(had_fix, rmc_void)
    assert unchanged == had_fix


def test_apply_rmc_before_any_gga_fix_is_ignored() -> None:
    rmc = parse_rmc(_RMC_ACTIVE)
    assert rmc is not None
    fix = apply_rmc(GpsFix(), rmc)
    assert fix == GpsFix()
