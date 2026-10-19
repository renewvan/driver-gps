"""Fixture-sentence tests for nmea.py's pure parse/apply functions -- no
serial hardware or MQTT broker required.

Prior art: node-tank's tests/test_calibration.py (fixture input, pure
function, no I/O).
"""

from node_gps.nmea import (
    GpsFix,
    apply_gga,
    apply_gsv,
    apply_rmc,
    gsv_snr_values,
    parse_gga,
    parse_gsv,
    parse_rmc,
)

_GGA_FIX = "$GPGGA,123456.00,4527.852,N,00911.400,E,1,08,0.9,122.3,M,45.9,M,,*66"
_GGA_NO_FIX = "$GPGGA,123456.00,,,,,0,00,99.99,,M,,M,,*61"
_RMC_ACTIVE = "$GPRMC,123456.00,A,4527.852,N,00911.400,E,33.7,184.7,041026,,,A*63"
_RMC_VOID = "$GPRMC,123456.00,V,,,,,,,,,,N*7A"
_GSV_GPS = "$GPGSV,1,1,03,10,45,110,38,15,60,220,42,21,30,300,35*40"
_GSV_GLONASS = "$GLGSV,1,1,02,65,20,150,30,70,55,280,44*6C"
_GSV_PARTIAL_TRACK = "$GPGSV,1,1,02,10,45,110,,15,60,220,*79"


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


def test_parse_gsv_rejects_non_gsv_sentence() -> None:
    assert parse_gsv(_GGA_FIX) is None


def test_gsv_snr_values_skips_empty_and_untracked_slots() -> None:
    gsv = parse_gsv(_GSV_GPS)
    assert gsv is not None
    assert gsv_snr_values(gsv) == [38.0, 42.0, 35.0]


def test_gsv_snr_values_skips_satellites_with_no_decoded_snr() -> None:
    gsv = parse_gsv(_GSV_PARTIAL_TRACK)
    assert gsv is not None
    assert gsv_snr_values(gsv) == []


def test_apply_gsv_averages_across_sentences_and_constellations() -> None:
    gps_gsv = parse_gsv(_GSV_GPS)
    glonass_gsv = parse_gsv(_GSV_GLONASS)
    assert gps_gsv is not None and glonass_gsv is not None
    snr_values = gsv_snr_values(gps_gsv) + gsv_snr_values(glonass_gsv)
    fix = apply_gsv(GpsFix(), snr_values)
    assert fix.avg_snr_db == round((38 + 42 + 35 + 30 + 44) / 5, 1)


def test_apply_gsv_with_no_readings_leaves_fix_unchanged() -> None:
    fix = GpsFix(avg_snr_db=37.5)
    assert apply_gsv(fix, []) == fix


def test_apply_gga_no_fix_preserves_avg_snr_db() -> None:
    gga = parse_gga(_GGA_FIX)
    no_fix_gga = parse_gga(_GGA_NO_FIX)
    assert gga is not None and no_fix_gga is not None
    gsv = parse_gsv(_GSV_GPS)
    assert gsv is not None
    had_fix_and_signal = apply_gsv(apply_gga(GpsFix(), gga), gsv_snr_values(gsv))
    cleared = apply_gga(had_fix_and_signal, no_fix_gga)
    assert cleared.fix_quality == "no_fix"
    assert cleared.avg_snr_db == had_fix_and_signal.avg_snr_db

