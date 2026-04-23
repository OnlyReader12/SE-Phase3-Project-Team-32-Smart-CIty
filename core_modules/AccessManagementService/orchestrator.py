"""
orchestrator.py — Dynamic Load Scaling Orchestrator

Manages a pool of ingestion service workers and distributes incoming IoT data
via round-robin. Auto-scales workers based on throughput:
  - Scale UP:   records/sec > 20 × worker_count → spawn new worker (max 4)
  - Scale DOWN: records/sec < 5 × worker_count and workers > 1 → kill one

Usage:
  python3 orchestrator.py
  python3 orchestrator.py --min-workers 1 --max-workers 4 --gateway-port 8005
"""

import argparse, os, signal, socket, subprocess, sys, time, threading, json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════
# Worker Management
# ═══════════════════════════════════════════

class Worker:
    def __init__(self, worker_id, port, proc):
        self.id = worker_id
        self.port = port
        self.proc = proc
        self.url = f"http://127.0.0.1:{port}"
        self.started_at = time.time()
        self.healthy = False

    def check_health(self):
        try:
            r = urlopen(f"{self.url}/health", timeout=2)
            self.healthy = r.getcode() == 200
        except:
            self.healthy = False
        return self.healthy


class WorkerPool:
    def __init__(self, min_w=1, max_w=4, gateway_port=8005):
        self.workers = []
        self.min_workers = min_w
        self.max_workers = max_w
        self.gateway_port = gateway_port
        self.rr_index = 0  # round-robin
        self.scale_decisions = []
        self._lock = threading.Lock()
        self._next_id = 0

    def _find_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def spawn_worker(self):
        with self._lock:
            if len(self.workers) >= self.max_workers:
                return None
            port = self._find_port()
            wid = f"w{self._next_id}"
            self._next_id += 1
            env = {**os.environ, "INGESTION_SERVICE_PORT": str(port), "WORKER_ID": wid}
            proc = subprocess.Popen(
                [sys.executable, "ingestion_service.py"],
                cwd=SCRIPT_DIR, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            threading.Thread(target=lambda: [None for _ in iter(proc.stdout.readline, "")], daemon=True).start()
            w = Worker(wid, port, proc)
            self.workers.append(w)
            self.scale_decisions.append({
                "action": "SCALE_UP",
                "worker": wid,
                "port": port,
                "total": len(self.workers),
                "time": datetime.now().isoformat(),
            })
            return w

    def kill_worker(self):
        with self._lock:
            if len(self.workers) <= self.min_workers:
                return None
            w = self.workers.pop()
            w.proc.terminate()
            try:
                w.proc.wait(timeout=3)
            except:
                w.proc.kill()
            self.scale_decisions.append({
                "action": "SCALE_DOWN",
                "worker": w.id,
                "total": len(self.workers),
                "time": datetime.now().isoformat(),
            })
            return w

    def get_next(self):
        """Round-robin selection of healthy worker."""
        with self._lock:
            healthy = [w for w in self.workers if w.healthy]
            if not healthy:
                healthy = self.workers
            if not healthy:
                return None
            w = healthy[self.rr_index % len(healthy)]
            self.rr_index += 1
            return w

    def get_primary(self):
        """First worker — used for control/fleet queries."""
        with self._lock:
            return self.workers[0] if self.workers else None

    def get_stats(self):
        """Aggregate engine-health from all workers."""
        total_ingested = 0
        total_rps = 0
        all_latencies = []
        for w in self.workers:
            try:
                r = urlopen(f"{w.url}/engine-health", timeout=2)
                d = json.loads(r.read())
                total_ingested += d.get("total_ingested", 0)
                total_rps += d.get("records_per_second", 0)
                all_latencies.append(d.get("avg_latency_ms", 0))
            except:
                pass
        return {
            "worker_count": len(self.workers),
            "total_ingested": total_ingested,
            "aggregate_rps": round(total_rps, 2),
            "avg_latency_ms": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0,
        }

    def shutdown_all(self):
        for w in self.workers:
            w.proc.terminate()
        for w in self.workers:
            try:
                w.proc.wait(timeout=3)
            except:
                w.proc.kill()
        self.workers.clear()

    def status(self):
        return {
            "workers": [{
                "id": w.id, "port": w.port, "healthy": w.healthy,
                "url": w.url, "uptime_s": round(time.time() - w.started_at),
            } for w in self.workers],
            "active": len(self.workers),
            "min": self.min_workers,
            "max": self.max_workers,
            "rr_index": self.rr_index,
            "recent_decisions": self.scale_decisions[-10:],
        }


# ═══════════════════════════════════════════
# Auto-Scaler Thread
# ═══════════════════════════════════════════

def auto_scaler(pool, stop_event, interval=10):
    """Monitor throughput and scale workers up/down."""
    C_G = '\033[92m'; C_Y = '\033[93m'; C_R = '\033[91m'; C_CY = '\033[96m'; C_END = '\033[0m'; C_BOLD = '\033[1m'
    while not stop_event.is_set():
        time.sleep(interval)
        try:
            stats = pool.get_stats()
            rps = stats["aggregate_rps"]
            wc = stats["worker_count"]

            # Scale UP
            if rps > 20 * wc and wc < pool.max_workers:
                w = pool.spawn_worker()
                if w:
                    time.sleep(3)  # wait for worker to boot
                    w.check_health()
                    print(f"  {C_CY}[SCALE] ⬆️ Spawned worker {w.id} on port {w.port} (RPS={rps:.1f}, workers={len(pool.workers)}){C_END}")

            # Scale DOWN
            elif rps < 5 * wc and wc > pool.min_workers:
                killed = pool.kill_worker()
                if killed:
                    print(f"  {C_Y}[SCALE] ⬇️ Killed worker {killed.id} (RPS={rps:.1f}, workers={len(pool.workers)}){C_END}")

            # Health check all
            for w in pool.workers:
                w.check_health()

        except Exception as e:
            print(f"  {C_R}[SCALE] Error: {e}{C_END}")


# ═══════════════════════════════════════════
# Orchestrator HTTP Server
# ═══════════════════════════════════════════

pool = None  # Will be set in main()

class OrchestratorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if self.path == "/scaling-status":
            self._json_response(pool.status())
        elif self.path == "/health":
            self._json_response({"status": "healthy", "service": "Orchestrator", "workers": len(pool.workers)})
        elif self.path == "/aggregate-health":
            self._json_response(pool.get_stats())
        else:
            self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/scale-up":
            w = pool.spawn_worker()
            if w:
                time.sleep(2)
                w.check_health()
                self._json_response({"status": "spawned", "worker": w.id, "port": w.port})
            else:
                self._json_response({"status": "at_max", "max": pool.max_workers}, 400)
        elif self.path == "/scale-down":
            w = pool.kill_worker()
            if w:
                self._json_response({"status": "killed", "worker": w.id})
            else:
                self._json_response({"status": "at_min", "min": pool.min_workers}, 400)
        else:
            self._json_response({"error": "Not found"}, 404)


def main():
    global pool
    C = type('C', (), {
        'G': '\033[92m', 'Y': '\033[93m', 'R': '\033[91m',
        'B': '\033[94m', 'CY': '\033[96m', 'END': '\033[0m',
        'BOLD': '\033[1m', 'DIM': '\033[2m',
    })

    ap = argparse.ArgumentParser()
    ap.add_argument("--min-workers", type=int, default=1)
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--gateway-port", type=int, default=8005)
    ap.add_argument("--orch-port", type=int, default=9000)
    args = ap.parse_args()

    pool = WorkerPool(min_w=args.min_workers, max_w=args.max_workers, gateway_port=args.gateway_port)

    print(f"\n{C.CY}{'═'*60}{C.END}")
    print(f"  {C.BOLD}🔀 Smart City Orchestrator — Dynamic Load Scaling{C.END}")
    print(f"  {C.DIM}Workers: {args.min_workers}-{args.max_workers} | Port: {args.orch_port}{C.END}")
    print(f"{C.CY}{'═'*60}{C.END}\n")

    # Start initial worker
    w = pool.spawn_worker()
    if not w:
        print(f"  {C.R}Failed to spawn initial worker{C.END}")
        return

    # Wait for health
    deadline = time.time() + 15
    while time.time() < deadline:
        if w.check_health():
            break
        time.sleep(1)
    else:
        print(f"  {C.R}Initial worker didn't become healthy{C.END}")
        pool.shutdown_all()
        return

    print(f"  {C.G}[OK] Initial worker {w.id} healthy on port {w.port}{C.END}")
    print(f"  {C.B}Orchestrator: http://127.0.0.1:{args.orch_port}/scaling-status{C.END}")
    print(f"  {C.B}Worker:       {w.url}/health{C.END}")
    print(f"\n  {C.DIM}Auto-scaling enabled: checking every 10s{C.END}")
    print(f"  {C.DIM}Scale UP:   RPS > 20 × workers  |  Scale DOWN: RPS < 5 × workers{C.END}")
    print(f"  {'─'*58}\n")

    # Start auto-scaler
    stop = threading.Event()
    scale_thread = threading.Thread(target=auto_scaler, args=(pool, stop), daemon=True)
    scale_thread.start()

    # Start orchestrator HTTP server
    server = HTTPServer(("127.0.0.1", args.orch_port), OrchestratorHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        print(f"  {C.Y}Running. Ctrl+C to stop.{C.END}")
        while True:
            time.sleep(15)
            s = pool.get_stats()
            status = pool.status()
            healthy = sum(1 for w in status["workers"] if w["healthy"])
            print(f"  {C.DIM}[ORCH] Workers: {s['worker_count']} ({healthy} healthy) | "
                  f"RPS: {s['aggregate_rps']} | Total: {s['total_ingested']} | "
                  f"Lat: {s['avg_latency_ms']}ms{C.END}")
    except KeyboardInterrupt:
        print(f"\n\n  {C.Y}Shutting down...{C.END}")
    finally:
        stop.set()
        server.shutdown()
        pool.shutdown_all()
        print(f"  {C.G}Done. All workers stopped.{C.END}\n")


if __name__ == "__main__":
    main()
