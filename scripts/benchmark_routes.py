"""Reproducible local planner timings and hard-closure checks; no live data writes."""

import argparse
import json
import math
import platform
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api/src"))

from werms_api.network import build_network
from werms_api.operations import Operations
from werms_api.scenarios import compare_scenario
from werms_api.schemas import RouteRequest, ScenarioRequest


def benchmark(iterations: int) -> dict:
    network = build_network()
    samples, scenarios, routes, violations = [], [], 0, 0
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="werms-benchmark-", dir=temp_root) as directory:
        store = Operations(Path(directory) / "isolated.sqlite3", network=network)
        for origin in network["origins"]:
            request = RouteRequest(origin_node_id=origin["node"], party_size=4)
            store.preview(request)  # Explicit warm-up, excluded from timing.
            for _ in range(iterations):
                start = perf_counter()
                plans = store.preview(request)
                samples.append((perf_counter() - start) * 1000)
                routes += len(plans)
            chosen = plans[0]
            blocked = chosen.edge_ids[len(chosen.edge_ids) // 2]
            result = compare_scenario(
                store,
                ScenarioRequest(**request.model_dump(), blocked_edge_ids=[blocked]),
            )
            violations += sum(blocked in p["edge_ids"] for p in result["simulated"])
            scenarios.append(
                {
                    "origin": origin["name"],
                    "outcome": result["outcome"],
                    "before": result["reachable_before"],
                    "after": result["reachable_after"],
                    "compute_ms": result["compute_ms"],
                }
            )
    ordered = sorted(samples)
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "road_version": network["version"],
        "nodes": len(network["nodes"]),
        "physical_road_segments": len(network["roads"]),
        "sample_count": len(samples),
        "routes_evaluated": routes,
        "median_ms": round(statistics.median(samples), 2),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
        "max_ms": round(max(samples), 2),
        "hard_closure_violations": violations,
        "scenario_checks": scenarios,
        "method": "Sequential warm planner calls across three origins, party=4, isolated SQLite; not HTTP, load or emergency-safety certification.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.iterations <= 100:
        parser.error("iterations must be between 2 and 100")
    result = benchmark(args.iterations)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
