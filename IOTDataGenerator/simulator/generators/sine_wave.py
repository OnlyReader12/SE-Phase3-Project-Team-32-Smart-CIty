"""
Sine wave signal generator keyed to wall-clock time.
Ideal for periodic real-world phenomena with daily/hourly cycles:
  - Solar irradiance (peaks at noon)
  - Outdoor temperature (peaks ~2PM)
  - Soil moisture (lowest in afternoon)
  - Battery SoC (inverse of solar curve)
"""
import math
import time


class SineWave:
    """
    Produces a time-varying sine signal: offset + amplitude * sin(2π·t / period).

    Args:
        amplitude:  Peak deviation from offset (half the peak-to-peak range).
        offset:     Vertical centre of the oscillation.
        period_s:   Length of one full cycle in seconds.
                    Use 86400 for daily cycles.
        phase_h:    Phase shift expressed in hours.
                    e.g. phase_h=12 makes the peak occur around hour 12 (noon).
        lo:         Optional hard lower clamp.
        hi:         Optional hard upper clamp.
    """

    def __init__(
        self,
        amplitude: float,
        offset: float,
        period_s: float,
        phase_h: float = 0.0,
        lo: float = None,
        hi: float = None,
    ):
        self.amplitude = float(amplitude)
        self.offset = float(offset)
        self.period_s = float(period_s)
        self.phase_s = float(phase_h) * 3600.0
        self.lo = lo
        self.hi = hi

    def value_at(self, epoch: float = None) -> float:
        """
        Evaluate the sine at the given POSIX timestamp.
        If epoch is None, uses the current wall-clock time.
        """
        if epoch is None:
            epoch = time.time()
        t = epoch + self.phase_s
        raw = self.offset + self.amplitude * math.sin(
            2.0 * math.pi * t / self.period_s
        )
        if self.lo is not None:
            raw = max(self.lo, raw)
        if self.hi is not None:
            raw = min(self.hi, raw)
        return round(raw, 3)

    def next(self) -> float:
        """Convenience alias: same interface as RandomWalk / StepChange."""
        return self.value_at()
