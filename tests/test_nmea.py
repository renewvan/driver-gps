"""Fixture-sentence tests for nmea.py's pure parse/apply functions -- no
serial hardware or MQTT broker required.

Prior art: driver-tank's tests/test_calibration.py (fixture input, pure
function, no I/O).
"""

from driver_gps.nmea import (
    GpsFix,
    Satellite,
    apply_gga,
    apply_gsv,
    apply_rmc,
    apply_satellites,
    gsv_satellites,
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


_GSV_BEIDOU = "$BDGSV,1,1,01,23,05,012,25*59"
_GSV_NONE_IN_VIEW = "$GPGSV,1,1,00*79"


def _satellites(*sentences: str) -> list[Satellite]:
    out: list[Satellite] = []
    for sentence in sentences:
        gsv = parse_gsv(sentence)
        assert gsv is not None, sentence
        out.extend(gsv_satellites(gsv))
    return out


def test_gsv_satellites_maps_talker_to_constellation_and_keeps_every_field() -> None:
    assert _satellites(_GSV_GPS, _GSV_GLONASS) == [
        Satellite("gps", 10, 38.0, 45, 110),
        Satellite("gps", 15, 42.0, 60, 220),
        Satellite("gps", 21, 35.0, 30, 300),
        Satellite("glonass", 65, 30.0, 20, 150),
        Satellite("glonass", 70, 44.0, 55, 280),
    ]


def test_gsv_satellites_maps_beidou_bd_talker() -> None:
    assert _satellites(_GSV_BEIDOU) == [Satellite("beidou", 23, 25.0, 5, 12)]


def test_gsv_satellites_keeps_a_satellite_with_no_snr_as_none_not_zero() -> None:
    # gsv_snr_values drops these; the satellite is still in view, so it must be listed.
    assert _satellites(_GSV_PARTIAL_TRACK) == [
        Satellite("gps", 10, None, 45, 110),
        Satellite("gps", 15, None, 60, 220),
    ]


def test_gsv_satellites_for_a_zero_satellite_sentence_is_empty() -> None:
    assert _satellites(_GSV_NONE_IN_VIEW) == []


def test_apply_satellites_dedupes_the_repeated_gsv_set_and_sorts() -> None:
    # The receiver repeats each constellation's set every second: a 3 s window holds 3 copies.
    window = _satellites(_GSV_GLONASS, _GSV_GPS, _GSV_GLONASS, _GSV_GPS, _GSV_GLONASS, _GSV_GPS)
    fix = apply_satellites(GpsFix(), window, saw_gsv=True)
    assert fix.satellites is not None
    assert [(s.constellation, s.prn) for s in fix.satellites] == [
        ("glonass", 65),
        ("glonass", 70),
        ("gps", 10),
        ("gps", 15),
        ("gps", 21),
    ]


def test_apply_satellites_latest_report_of_a_satellite_wins() -> None:
    earlier = [Satellite("gps", 10, 20.0, 45, 110)]
    later = [Satellite("gps", 10, 38.0, 46, 111)]
    fix = apply_satellites(GpsFix(), earlier + later, saw_gsv=True)
    assert fix.satellites == (Satellite("gps", 10, 38.0, 46, 111),)


def test_apply_satellites_drops_a_satellite_absent_from_the_new_window() -> None:
    had = apply_satellites(GpsFix(), _satellites(_GSV_GPS, _GSV_GLONASS), saw_gsv=True)
    now = apply_satellites(had, _satellites(_GSV_GLONASS), saw_gsv=True)
    assert now.satellites is not None
    assert {s.constellation for s in now.satellites} == {"glonass"}


def test_apply_satellites_with_no_gsv_in_window_keeps_the_last_sky() -> None:
    had = apply_satellites(GpsFix(), _satellites(_GSV_GPS), saw_gsv=True)
    assert apply_satellites(had, [], saw_gsv=False) == had


def test_apply_satellites_with_gsv_but_nothing_in_view_is_empty_not_absent() -> None:
    fix = apply_satellites(GpsFix(), _satellites(_GSV_NONE_IN_VIEW), saw_gsv=True)
    assert fix.satellites == ()


def test_apply_satellites_is_absent_before_any_gsv() -> None:
    assert apply_satellites(GpsFix(), [], saw_gsv=False).satellites is None


def test_apply_gga_no_fix_preserves_satellites() -> None:
    gga = parse_gga(_GGA_FIX)
    no_fix_gga = parse_gga(_GGA_NO_FIX)
    assert gga is not None and no_fix_gga is not None
    seen = apply_satellites(apply_gga(GpsFix(), gga), _satellites(_GSV_GPS), saw_gsv=True)
    cleared = apply_gga(seen, no_fix_gga)
    assert cleared.fix_quality == "no_fix"
    assert cleared.satellites == seen.satellites
