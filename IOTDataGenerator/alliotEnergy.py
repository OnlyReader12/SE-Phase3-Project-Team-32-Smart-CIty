"""
alliotEnergy.py — Continuous Energy Node Stream (All Node Types + Random Values)

Simulates all Energy node types (power monitors, solar, battery, etc.)
generating continuous random payloads for realtime visualization and testing.

This is the Energy domain equivalent of allIOTResult.py (which handles EHS nodes).
"""

from iot_generator import EnergyNode
from iot_result_common import SilentAdapter, run_all_node_stream


def build_energy_node_factories():
    """
    Factory functions for all energy node types.
    Each returns a fresh node instance ready to generate random payloads.
    """
    return {
        "Power Monitor 1": lambda: EnergyNode("PWR-NODE-001", SilentAdapter()),
        "Power Monitor 2": lambda: EnergyNode("PWR-NODE-002", SilentAdapter()),
        "Power Monitor 3": lambda: EnergyNode("PWR-NODE-003", SilentAdapter()),
        "Power Monitor 4": lambda: EnergyNode("PWR-NODE-004", SilentAdapter()),
        "Power Monitor 5": lambda: EnergyNode("PWR-NODE-005", SilentAdapter()),
    }


if __name__ == "__main__":
    print("=" * 72)
    print("Energy Node Stream — Continuous Random Data")
    print("Domain: energy | Node Type: power_monitor")
    print("=" * 72)
    run_all_node_stream(build_energy_node_factories(), interval_seconds=1.2)
