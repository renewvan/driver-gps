"""Publish loop: NMEA read -> renewvan/gps/<id>/<property>.

Field shape per hub's schema/gps.schema.json: this node owns the sensing
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

from node_gps.config import AppConfig
from node_gps.node_info import build_info_payload
from node_gps.publisher import Publisher
from node_gps.serial_reader import SerialReader

logger = logging.getLogger(__name__)


def _topic(node_id: str, prop: str) -> str:
    return f"renewvan/gps/{node_id}/{prop}"


def read_and_publish(publisher: Publisher, reader: SerialReader, config: AppConfig) -> None:
    """Read the latest NMEA fix and publish every live field.

    fix_quality/satellites_in_use/avg_snr_db are published whenever
    available (avg_snr_db is independent of fix_quality -- it may be
    absent on the very first poll before any GSV sentence has streamed
    through); every other field is published only once a fix is acquired
    (fix_quality != "no_fix") -- matches hub/schema/gps.schema.json's
    conditional-optional fields.
    """
    fix = reader.read_fix(config.node.read_timeout_s)
    node_id = config.node.id

    publisher.publish(_topic(node_id, "fix_quality"), json.dumps(fix.fix_quality))
    publisher.publish(_topic(node_id, "satellites_in_use"), json.dumps(fix.satellites_in_use))
    if fix.avg_snr_db is not None:
        publisher.publish(_topic(node_id, "avg_snr_db"), json.dumps(fix.avg_snr_db))

    if fix.fix_quality == "no_fix":
        logger.info(
            "gps=%s fix_quality=no_fix satellites_in_use=%d avg_snr_db=%s",
            node_id,
            fix.satellites_in_use,
            fix.avg_snr_db,
        )
        return

    publisher.publish(_topic(node_id, "latitude"), json.dumps(fix.latitude))
    publisher.publish(_topic(node_id, "longitude"), json.dumps(fix.longitude))
    if fix.altitude_m is not None:
        publisher.publish(_topic(node_id, "altitude_m"), json.dumps(round(fix.altitude_m, 1)))
    if fix.hdop is not None:
        publisher.publish(_topic(node_id, "hdop"), json.dumps(fix.hdop))
    if fix.speed_kmh is not None:
        publisher.publish(_topic(node_id, "speed_kmh"), json.dumps(round(fix.speed_kmh, 1)))
    if fix.course_deg is not None:
        publisher.publish(_topic(node_id, "course_deg"), json.dumps(round(fix.course_deg, 1)))
    if fix.fix_time is not None:
        publisher.publish(_topic(node_id, "fix_time"), json.dumps(fix.fix_time))

    logger.info(
        "gps=%s fix_quality=%s lat=%.6f lon=%.6f speed_kmh=%s sats=%d",
        node_id,
        fix.fix_quality,
        fix.latitude,
        fix.longitude,
        fix.speed_kmh,
        fix.satellites_in_use,
    )


def run(config: AppConfig) -> None:
    # Host serial is read once, here: Publisher republishes this same payload on every reconnect.
    info_payload = build_info_payload(env=os.environ, cpuinfo_path=Path("/proc/cpuinfo"))
    publisher = Publisher(config.mqtt, info_payload)
    publisher.connect()
    reader = SerialReader(config.node.serial_port, config.node.baud_rate)
    try:
        while True:
            try:
                read_and_publish(publisher, reader, config)
            except Exception:
                logger.exception("Read failed for gps=%s", config.node.id)
            time.sleep(config.node.update_interval_ms / 1000)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        reader.close()
        publisher.disconnect()
