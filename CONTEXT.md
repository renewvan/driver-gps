# driver-gps

Domain glossary for driver-gps: what each published field *means*,
independent of the Python that computes it.

## Language

**Fix**:
A single resolved position reading from the GPS/GLONASS/BeiDou module,
combining its most recent GGA (position/quality/satellites/altitude/HDOP)
and RMC (speed/course/UTC date-time) NMEA sentences. Everything this Driver
publishes under `renewvan/gps/<id>/` is derived from the current fix.
_Avoid_: Reading, sample (NMEA-specific term, not this project's vocabulary).

**fix_quality**:
Mapped 1:1 from the GGA sentence's fix-quality field (0–8) to a string
enum: `no_fix`, `gps`, `dgps`, `pps`, `rtk`, `float_rtk`, `estimated`,
`manual`, `simulation`. The single source of truth for whether a fix is
usable — `no_fix` means every other field (`latitude`, `longitude`,
`altitude_m`, `hdop`, `speed_kmh`, `course_deg`, `fix_time`) is absent,
not stale or zeroed.
_Avoid_: Fix type (NMEA term; this project calls it fix_quality to match
the published field name).

**Live field** (this Driver):
Every field driver-gps publishes is live — republished on every poll
(default 3s), with no identity/startup-only subset (contrast with
`driver-tank`, where `fluid_type`/`capacity_l` publish once). Position has
no meaningful "publish once" value; turning the live stream into a trip
history is the `logger` repo's job, not this Driver's.
_Avoid_: Identity field (doesn't apply to this Driver — don't invent one).

**driver**:
Attribution, not a measurement: the key of the Driver that publishes this
instance (`"gps"`, equal to manifest.json's `driver` and to the
`renewvan/gps/info` topic segment), published retained on
`renewvan/gps/<id>/driver`. It is the one field that is not derived from the
fix, so it is published on every poll even with `no_fix`.
_Avoid_: Device (a Driver is the software that publishes; the GPS module is
hardware).

**fix_time**:
UTC timestamp of the fix, built from the RMC sentence's date+time fields.
Always carries an explicit `+00:00` offset — the GPS module's own clock is
UTC, never localized to the van's timezone. Present only when
`fix_quality != no_fix`.
_Avoid_: Timestamp (ambiguous with a local wall-clock time; this is
specifically the GPS-derived UTC fix time).

**speed_kmh / course_deg**:
Ground speed and track-made-good, both from the RMC sentence.
`speed_kmh` is converted from RMC's native knots (×1.852) — km/h is this
Driver's canonical unit, not knots, matching the "canonical SI-adjacent unit
in the published field name" convention `driver-tank` set with `capacity_l`.
`course_deg` is degrees true (not magnetic), 0–360.
_Avoid_: Heading (ambiguous with magnetic heading; RMC's course is track
made good over the ground, not where the antenna points).

**avg_snr_db**:
Mean carrier-to-noise ratio (C/N0, in dB-Hz) across every satellite with
a decoded SNR value in the GSV sentences seen during a poll, any
constellation (GPS/GLONASS/BeiDou). Unlike every other field besides
`fix_quality`/`satellites_in_use`, it's independent of fix status — a
module can be tracking satellites with real signal strength well before
(or without ever) acquiring a usable fix, and this field reflects that.
Not the same population as `satellites_in_use`: GSV's tracked-satellite
set isn't necessarily the exact subset GGA used for the fix.
_Avoid_: Signal strength (too generic — this project's field name is
avg_snr_db), RSSI (a different metric family; GPS receivers report C/N0,
not received signal strength).

**satellites**:
One retained array of every satellite the receiver lists in view in its GSV
sentences, any constellation: `{constellation, prn, snr_db, elevation_deg,
azimuth_deg}` each. The per-satellite detail behind `avg_snr_db`, and like it
independent of fix status. A satellite in view that the receiver is not yet
measuring keeps its entry with `snr_db: null` (never 0), unlike
`avg_snr_db`, which skips it. Rebuilt from each poll window and deduplicated
by `(constellation, prn)`, since the receiver repeats each constellation's
GSV set about once a second. Not the same population as `satellites_in_use`.
_Avoid_: Sky, sat list, tracked satellites (GSV lists satellites in view, not
only those the receiver is tracking with a signal).

**HDOP**:
Horizontal Dilution of Precision — a unitless multiplier on raw
horizontal position error, driven by satellite *geometry* (how spread
across the sky the satellites in use are), not signal strength. Low
(≤1–2) means well-spread satellites and a tight fix; high means
clustered satellites (e.g. sky mostly blocked on one side) and a loose
fix even with strong signal. From the GGA sentence. Present only when
`fix_quality != no_fix`.
_Avoid_: Accuracy, precision (HDOP is a multiplier on error, not an
error value itself — it has no units and isn't meters).
