# node-gps

Domain glossary for node-gps: what each published field *means*,
independent of the Python that computes it.

## Language

**Fix**:
A single resolved position reading from the GPS/GLONASS/BeiDou module,
combining its most recent GGA (position/quality/satellites/altitude/HDOP)
and RMC (speed/course/UTC date-time) NMEA sentences. Everything the node
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

**Live field** (this node):
Every field node-gps publishes is live — republished on every poll
(default 3s), with no identity/startup-only subset (contrast with
`node-tank`, where `fluid_type`/`capacity_l` publish once). Position has
no meaningful "publish once" value; turning the live stream into a trip
history is the `logger` repo's job, not this node's.
_Avoid_: Identity field (doesn't apply to this node — don't invent one).

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
node's canonical unit, not knots, matching the "canonical SI-adjacent unit
in the published field name" convention `node-tank` set with `capacity_l`.
`course_deg` is degrees true (not magnetic), 0–360.
_Avoid_: Heading (ambiguous with magnetic heading; RMC's course is track
made good over the ground, not where the antenna points).
