import datetime
import json
import time
import threading
from typing import Callable, Dict, Any


class SilentAdapter:
    def send(self, payload: Dict[str, Any]) -> None:
        pass


def run_node_samples(node_factory: Callable[[], Any], label: str, sample_count: int = 5, delay_seconds: float = 0.5) -> None:
    """Print sample payloads for a single node type to verify random variation."""
    node = node_factory()

    print("=" * 72)
    print(f"{label} Random Output Check")
    print(f"Node ID: {node.node_id} | Node Type: {node.node_type}")
    print("=" * 72)

    previous_data = None
    for i in range(sample_count):
        payload = node.generate_payload()
        data = payload.get("data", {})

        changed = previous_data is None or data != previous_data
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\nSample {i + 1}/{sample_count} @ {ts} | Changed from previous: {changed}")
        print(json.dumps(data, indent=2))

        previous_data = data
        time.sleep(delay_seconds)

    print("\nDone. If most samples show changed=True, random generation is working.")


def run_all_node_stream(node_factories: Dict[str, Callable[[], Any]], interval_seconds: float = 1.5) -> None:
    """Continuously print random payloads from all provided node factories."""
    stop_event = threading.Event()
    print_lock = threading.Lock()

    def worker(label: str, factory: Callable[[], Any]) -> None:
        node = factory()
        previous_data = None
        while not stop_event.is_set():
            payload = node.generate_payload()
            data = payload.get("data", {})
            changed = previous_data is None or data != previous_data
            previous_data = data
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            with print_lock:
                print(f"[{ts}] {label:20s} | node={node.node_id:16s} | changed={changed}")
                print(json.dumps(data, indent=2))
                print("-" * 72)
            time.sleep(interval_seconds)

    threads = [
        threading.Thread(target=worker, args=(label, factory), daemon=True)
        for label, factory in node_factories.items()
    ]

    print("=" * 72)
    print("All IoT Node Random Stream")
    print("Press Ctrl+C to stop")
    print("=" * 72)

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
        for t in threads:
            t.join(timeout=1.5)
        print("\nStopped all node streams.")
