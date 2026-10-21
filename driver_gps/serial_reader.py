"""Serial-port I/O: reads NMEA lines from the GPS module's USB-serial port
and folds them into a GpsFix via nmea.py's pure parsing functions.

Owns the one stateful piece this device has -- the latest GGA/RMC sentence
seen -- so a caller can poll read_fix() on a fixed interval and always get
the most recently decoded fix, even though the module streams sentences
continuously and asynchronously from the poll loop. Not unit-tested
directly (thin I/O glue, same as driver-tank's adc.py wrapper); nmea.py's
parse/apply functions carry the fixture-tested logic.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from driver_gps.nmea import (
    GpsFix,
    apply_gga,
    apply_gsv,
    apply_rmc,
    gsv_snr_values,
    parse_gga,
    parse_gsv,
    parse_rmc,
)

logger = logging.getLogger(__name__)


@dataclass
class SerialReader:
    port: str
    baud_rate: int

    def __post_init__(self) -> None:
        import serial  # imported lazily so tests never need a real serial port

        self._serial = serial.Serial(self.port, baudrate=self.baud_rate, timeout=1.0)
        self._fix = GpsFix()

    def read_fix(self, timeout_s: float) -> GpsFix:
        """Drain available NMEA lines for up to timeout_s, folding each GGA/RMC
        sentence seen onto the cached fix and accumulating every GSV
        sentence's SNR readings, then averaging the latter once at the
        end of the window. Returns the latest state.

        A device that's gone silent (unplugged, no satellite lock yet)
        simply returns the previously cached fix unchanged for this poll.
        """
        deadline = time.monotonic() + timeout_s
        snr_values: list[float] = []
        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            if gga := parse_gga(line):
                self._fix = apply_gga(self._fix, gga)
            elif rmc := parse_rmc(line):
                self._fix = apply_rmc(self._fix, rmc)
            elif gsv := parse_gsv(line):
                snr_values.extend(gsv_snr_values(gsv))
        self._fix = apply_gsv(self._fix, snr_values)
        return self._fix

    def close(self) -> None:
        self._serial.close()
