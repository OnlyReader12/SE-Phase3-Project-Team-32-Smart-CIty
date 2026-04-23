"""
EHS Engine — Concrete Engine
Declares the 5 rules for environmental health & safety analysis.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.base_engine import BaseEngine, AnalysisRule
from rules.air_quality       import AirQualityRule
from rules.indoor_comfort    import IndoorComfortRule
from rules.water_safety      import WaterSafetyRule
from rules.water_quality     import WaterQualityRule
from rules.equipment_health  import EquipmentHealthRule


class EHSEngine(BaseEngine):
    """
    Concrete engine for EHS domain.
    Adding Q6 (e.g., Noise Pollution) = drop noise_pollution.py in rules/, add here.
    """

    @property
    def engine_name(self) -> str:
        return "EHSEngine"

    def get_rules(self) -> list[AnalysisRule]:
        return [
            AirQualityRule(),
            IndoorComfortRule(),
            WaterSafetyRule(),
            WaterQualityRule(),
            EquipmentHealthRule(),
        ]

    def node_filter(self) -> dict:
        return {"engine_type": "ehs"}
