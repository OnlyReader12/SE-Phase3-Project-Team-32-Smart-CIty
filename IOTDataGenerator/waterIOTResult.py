from iot_generator import WaterQualityNode
from iot_result_common import SilentAdapter, run_node_samples


def make_node():
    return WaterQualityNode("EHS-WTR-RESULT", SilentAdapter())


if __name__ == "__main__":
    run_node_samples(make_node, "Water Quality Node", sample_count=6, delay_seconds=0.4)
