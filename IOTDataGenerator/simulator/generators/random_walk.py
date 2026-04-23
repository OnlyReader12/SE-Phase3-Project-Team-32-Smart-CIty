"""
Bounded random walk signal generator.
Each tick the value drifts by a random amount within [-step, +step],
clamped to [lo, hi]. Produces realistic slowly-varying sensor readings.
"""
import random


class RandomWalk:
    """
    Simulates sensors whose values change gradually over time:
    e.g. temperature, voltage, pH, water flow rate.

    Args:
        initial: Starting value.
        lo:      Hard lower bound (values never go below this).
        hi:      Hard upper bound (values never go above this).
        step:    Maximum change per tick (both directions).
    """

    def __init__(self, initial: float, lo: float, hi: float, step: float):
        self.value = float(initial)
        self.lo = float(lo)
        self.hi = float(hi)
        self.step = float(step)

    def next(self) -> float:
        """Advance the walk by one tick and return the new value."""
        delta = random.uniform(-self.step, self.step)
        self.value = max(self.lo, min(self.hi, self.value + delta))
        return round(self.value, 3)
