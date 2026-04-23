"""
Energy Management Engine — Concrete Engine
Declares the 5 rules for energy analysis. Never modifies BaseEngine.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.base_engine import BaseEngine, AnalysisRule
from rules.power_balance   import PowerBalanceRule
from rules.ac_efficiency   import ACEfficiencyRule
from rules.light_waste     import LightWasteRule
from rules.battery_health  import BatteryHealthRule
from rules.ev_peak_load    import EVPeakLoadRule


class EnergyManagementEngine(BaseEngine):
    """
    Concrete engine for energy domain.
    Adding Q6 = create a new rule file + add it to the list below. That's all.
    """

    @property
    def engine_name(self) -> str:
        return "EnergyManagementEngine"

    def get_rules(self) -> list[AnalysisRule]:
        return [
            PowerBalanceRule(),
            ACEfficiencyRule(),
            LightWasteRule(),
            BatteryHealthRule(),
            EVPeakLoadRule(),
        ]

    def node_filter(self) -> dict:
        return {"engine_type": "energy"}
