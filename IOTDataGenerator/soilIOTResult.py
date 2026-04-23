from iot_generator import SoilSensorNode
from iot_result_common import SilentAdapter, run_node_samples


def make_node():
    return SoilSensorNode("EHS-SOL-RESULT", SilentAdapter())


if __name__ == "__main__":
    run_node_samples(make_node, "Soil Sensor Node", sample_count=6, delay_seconds=0.4)
