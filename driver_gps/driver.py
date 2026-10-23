"""Publish loop: NMEA read -> renewvan/gps/<id>/<property>.

Field shape per hub's schema/gps.schema.json: this Driver owns the sensing
(reads a USB-serial GPS/GLONASS/BeiDou module directly, NMEA 0183 output)
rather than remapping an existing feed. Every published field is live --
republished every poll, matching the road-trip-tracking use case (no
identity/startup-only fields; see README's Topics published section).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from driver_gps.config import AppConfig
from driver_gps.driver_info import build_info_payload
from driver_gps.nmea import Satellite
from driver_gps.publisher import Publisher
from driver_gps.serial_reader import SerialReader

logger = logging.getLogger(__name__)

# This Driver's key: its repo name minus `driver-`, equal to manifest.json's `driver` and to the
# `renewvan/<key>/info` segment. Entity instances name it on `renewvan/gps/<id>/driver`.
DRIVER_KEY = "gps"


def _topic(instance_id: str, prop: str) -> str:
    return f"renewvan/gps/{instance_id}/{prop}"


def satellites_payload(satellites: tuple[Satellite, ...]) -> list[dict[str, object]]:
    """The `satellites` array exactly as hub/schema/gps.schema.json defines an item."""
    return [
        {
            "constellation": sat.constellation,
            "prn": sat.prn,
            "snr_db": sat.snr_db,
            "elevation_deg": sat.elevation_deg,
            "azimuth_deg": sat.azimuth_deg,
        }
        for sat in satellites
    ]


def read_and_publish(publisher: Publisher, reader: SerialReader, config: AppConfig) -> None:
    """Read the latest NMEA fix and publish every live field, plus `driver`.

    fix_quality/satellites_in_use/avg_snr_db/satellites are published whenever
    available (avg_snr_db and satellites are independent of fix_quality -- they
    may be absent on the very first poll before any GSV sentence has streamed
    through); every other field is published only once a fix is acquired
    (fix_quality != "no_fix") -- matches hub/schema/gps.schema.json's
    conditional-optional fields.
    """
    fix = reader.read_fix(config.driver.read_timeout_s)
    instance_id = config.driver.id

    # Retained attribution, republished with every other retained field so it is back after a
    # broker restart or reconnect (this instance has no startup-only identity fields).
    publisher.publish(_topic(instance_id, "driver"), json.dumps(DRIVER_KEY))
    publisher.publish(_topic(instance_id, "fix_quality"), json.dumps(fix.fix_quality))
    publisher.publish(_topic(instance_id, "satellites_in_use"), json.dumps(fix.satellites_in_use))
    if fix.avg_snr_db is not None:
        publisher.publish(_topic(instance_id, "avg_snr_db"), json.dumps(fix.avg_snr_db))
    if fix.satellites is not None:
        payload = json.dumps(satellites_payload(fix.satellites))
        publisher.publish(_topic(instance_id, "satellites"), payload)

    if fix.fix_quality == "no_fix":
        logger.info(
            "gps=%s fix_quality=no_fix satellites_in_use=%d avg_snr_db=%s",
            instance_id,
            fix.satellites_in_use,
            fix.avg_snr_db,
        )
        return

    publisher.publish(_topic(instance_id, "latitude"), json.dumps(fix.latitude))
    publisher.publish(_topic(instance_id, "longitude"), json.dumps(fix.longitude))
    if fix.altitude_m is not None:
        publisher.publish(_topic(instance_id, "altitude_m"), json.dumps(round(fix.altitude_m, 1)))
    if fix.hdop is not None:
        publisher.publish(_topic(instance_id, "hdop"), json.dumps(fix.hdop))
    if fix.speed_kmh is not None:
        publisher.publish(_topic(instance_id, "speed_kmh"), json.dumps(round(fix.speed_kmh, 1)))
    if fix.course_deg is not None:
        publisher.publish(_topic(instance_id, "course_deg"), json.dumps(round(fix.course_deg, 1)))
    if fix.fix_time is not None:
        publisher.publish(_topic(instance_id, "fix_time"), json.dumps(fix.fix_time))

    logger.info(
        "gps=%s fix_quality=%s lat=%.6f lon=%.6f speed_kmh=%s sats=%d",
        instance_id,
        fix.fix_quality,
        fix.latitude,
        fix.longitude,
        fix.speed_kmh,
        fix.satellites_in_use,
    )


def run(config: AppConfig) -> None:
    # Board serial is read once, here: Publisher republishes this same payload on every reconnect.
    info_payload = build_info_payload(env=os.environ, cpuinfo_path=Path("/proc/cpuinfo"))
    publisher = Publisher(config.mqtt, info_payload)
    publisher.connect()
    reader = SerialReader(config.driver.serial_port, config.driver.baud_rate)
    try:
        while True:
            try:
                read_and_publish(publisher, reader, config)
            except Exception:
                logger.exception("Read failed for gps=%s", config.driver.id)
            time.sleep(config.driver.update_interval_ms / 1000)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        reader.close()
        publisher.disconnect()
