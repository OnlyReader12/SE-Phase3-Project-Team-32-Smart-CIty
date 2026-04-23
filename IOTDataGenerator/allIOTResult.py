from iot_generator import (
    AirQualityNode,
    WaterQualityNode,
    NoiseMonitorNode,
    WeatherStationNode,
    SoilSensorNode,
    RadiationGasNode,
)
from iot_result_common import SilentAdapter, run_all_node_stream


def build_node_factories():
    return {
        "Air Quality": lambda: AirQualityNode("EHS-AQI-ALL", SilentAdapter()),
        "Water Quality": lambda: WaterQualityNode("EHS-WTR-ALL", SilentAdapter()),
        "Noise Monitor": lambda: NoiseMonitorNode("EHS-NOS-ALL", SilentAdapter()),
        "Weather Station": lambda: WeatherStationNode("EHS-WEA-ALL", SilentAdapter()),
        "Soil Sensor": lambda: SoilSensorNode("EHS-SOL-ALL", SilentAdapter()),
        "Radiation/Gas": lambda: RadiationGasNode("EHS-RAD-ALL", SilentAdapter()),
    }


if __name__ == "__main__":
    run_all_node_stream(build_node_factories(), interval_seconds=1.2)
