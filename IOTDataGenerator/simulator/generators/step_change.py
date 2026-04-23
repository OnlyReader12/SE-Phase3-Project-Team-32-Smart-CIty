"""
Probabilistic discrete state-machine generator.
Each tick there is a small chance (flip_prob) of transitioning to a
different state from the current one.

Intended for:
  - ON / OFF states (lights, pumps, AC units)
  - OPEN / CLOSED valves
  - Enum-like sensor flags (SAFE / MODERATE / CRITICAL)
  - Boolean leak_detected, fault_status
"""
import random


class StepChange:
    """
    Holds a stable discrete state and occasionally flips to another.

    Args:
        states:    List of possible states (strings, ints, bools, etc.)
        initial:   The initial state (must be in states).
        flip_prob: Probability per tick of changing state. Default 0.02 (2% chance).
    """

    def __init__(self, states: list, initial, flip_prob: float = 0.02):
        if not states:
            raise ValueError("StepChange requires at least one state.")
        self.states = list(states)
        self.state = initial
        self.flip_prob = float(flip_prob)

    def next(self):
        """Possibly flip to a different state and return the current state."""
        if random.random() < self.flip_prob:
            other = [s for s in self.states if s != self.state]
            if other:
                self.state = random.choice(other)
        return self.state
