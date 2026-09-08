# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Named experiments, controller comparison, Monte Carlo, counterfactuals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from plantos.config import (
    ControllerType,
    ExperimentConfig,
    FaultSpec,
    SensorChannelConfig,
    load_experiment_config,
)
from plantos.simulation.engine import SimulationResult, run_experiment
from plantos.simulation.metrics import metrics_to_dict


def _scenario_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        Path.cwd() / "scenarios",
        here.parents[3] / "scenarios" if len(here.parents) > 3 else Path("scenarios"),
        here.parents[2] / "scenarios",
    ]


def scenario_path(name: str) -> Path:
    p = Path(name)
    if p.suffix in {".yaml", ".yml"} and p.exists():
        return p
    for d in _scenario_dirs():
        cand = d / f"{name}.yaml"
        if cand.exists():
            return cand
    raise FileNotFoundError(f"Scenario not found: {name}")


def load_scenario(name: str, controller: str | None = None, seed: int | None = None) -> ExperimentConfig:
    cfg = load_experiment_config(scenario_path(name))
    if controller:
        cfg.controller = ControllerType(controller.lower())
    if seed is not None:
        cfg.simulation.seed = seed
    return cfg


def simulate(name: str, controller: str = "mpc", seed: int | None = None) -> SimulationResult:
    return run_experiment(load_scenario(name, controller, seed))


def compare_controllers(name: str, seed: int | None = None) -> dict[str, Any]:
    rows = {}
    results: dict[str, SimulationResult] = {}
    for ctrl in ("naive", "rules", "mpc"):
        res = simulate(name, ctrl, seed)
        results[ctrl] = res
        rows[ctrl] = metrics_to_dict(res.metrics)
    return {
        "scenario": name,
        "seed": seed if seed is not None else load_scenario(name).simulation.seed,
        "controllers": rows,
        "events": {k: [e.to_dict() for e in results[k].events[:40]] for k in results},
        "results": results,
    }


def counterfactual(name: str, seed: int | None = None) -> dict[str, Any]:
    """Identical disturbance: naive (without PlantOS) vs MPC (with PlantOS)."""
    without = simulate(name, "naive", seed)
    with_os = simulate(name, "mpc", seed)
    lost_without = _lost_production(without)
    lost_with = _lost_production(with_os)
    return {
        "scenario": name,
        "without_plantos": {
            "controller": "naive",
            "metrics": metrics_to_dict(without.metrics),
            "narrative": _narrative(without, "WITHOUT PlantOS"),
            "lost_production_kg": lost_without,
        },
        "with_plantos": {
            "controller": "mpc",
            "metrics": metrics_to_dict(with_os.metrics),
            "narrative": _narrative(with_os, "WITH PlantOS"),
            "lost_production_kg": lost_with,
        },
        "methane_saved_kg": with_os.metrics.methane_total_kg - without.metrics.methane_total_kg,
        "downtime_avoided_hours": without.metrics.downtime_hours - with_os.metrics.downtime_hours,
    }


def _lost_production(res: SimulationResult) -> float:
    rates = [s.methane_rate_kgph for s in res.states]
    if not rates:
        return 0.0
    peak = max(rates)
    return float(sum(max(peak - r, 0.0) for r in rates))


def _narrative(res: SimulationResult, title: str) -> list[str]:
    m = res.metrics
    lines = [title]
    if m.min_soc < 0.15:
        lines.append("Battery approached reserve / depletion")
    if m.downtime_hours > 1:
        lines.append(f"{m.downtime_hours:.1f} hours degraded or emergency downtime")
    else:
        lines.append("No extended emergency downtime")
    lines.append(f"Methane produced: {m.methane_total_kg:.0f} kg")
    lines.append(f"Curtailment: {100 * m.curtailment_fraction:.1f}% of available solar")
    lines.append(f"Survival score: {m.survival_score:.3f}")
    if m.recovery_hours is not None:
        lines.append(f"Recovery after {m.recovery_hours:.1f} h")
    return lines


def _randomize_config(base: ExperimentConfig, rng: np.random.Generator) -> ExperimentConfig:
    cfg = ExperimentConfig.model_validate(base.model_dump())
    cfg.simulation.seed = int(rng.integers(1, 10_000_000))
    cfg.weather.scenario = str(rng.choice(["mixed", "cloudy", "clear", "storm", "cascade"]))
    cfg.forecast.bias_wm2 = float(rng.uniform(-20, 90))
    cfg.forecast.noise_std_wm2 = float(rng.uniform(30, 110))
    cfg.forecast.ar1_phi = float(rng.uniform(0.5, 0.9))
    if rng.random() < 0.35:
        cfg.forecast.failure_start_hour = float(rng.uniform(24, 180))
        cfg.forecast.failure_duration_hours = float(rng.uniform(4, 18))
    cfg.plant.battery.initial_soh = float(rng.uniform(0.82, 1.0))
    cfg.plant.battery.initial_soc = float(rng.uniform(0.35, 0.7))
    cfg.plant.electrolyser.initial_health = float(rng.uniform(0.88, 1.0))
    cfg.sensors.solar_power = SensorChannelConfig(noise_std=float(rng.uniform(0.02, 0.08)))
    cfg.sensors.battery_soc = SensorChannelConfig(noise_std=float(rng.uniform(0.004, 0.015)))
    cfg.sensors.hydrogen_flow = SensorChannelConfig(noise_std=float(rng.uniform(0.8, 3.0)))

    faults: list[FaultSpec] = []
    if rng.random() < 0.7:
        faults.append(
            FaultSpec(
                type=str(
                    rng.choice(
                        [
                            "electrolyser_efficiency",
                            "electrolyser_partial",
                            "battery_capacity",
                            "co2_reduced",
                            "solar_shading",
                            "methanation_throughput",
                        ]
                    )
                ),
                start_hour=float(rng.uniform(12, 200)),
                severity=float(rng.uniform(0.15, 0.45)),
            )
        )
    if rng.random() < 0.35:
        faults.append(
            FaultSpec(
                type=str(rng.choice(["sensor_drift", "sensor_bias", "sensor_frozen"])),
                start_hour=float(rng.uniform(24, 200)),
                severity=float(rng.uniform(0.3, 1.5)),
                component=str(rng.choice(["hydrogen_flow", "electrolyser_power", "battery_soc"])),
            )
        )
    cfg.faults.faults = faults
    cfg.mpc.horizon_hours = 24
    return cfg


def monte_carlo(
    n_runs: int = 100,
    base_scenario: str = "baseline",
    seed: int = 123,
    controllers: tuple[str, ...] = ("naive", "rules", "mpc"),
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    base = load_scenario(base_scenario)
    per_ctrl: dict[str, list[dict[str, Any]]] = {c: [] for c in controllers}
    for _ in range(n_runs):
        randomized = _randomize_config(base, rng)
        for ctrl in controllers:
            cfg = ExperimentConfig.model_validate(randomized.model_dump())
            cfg.controller = ControllerType(ctrl)
            res = run_experiment(cfg)
            per_ctrl[ctrl].append(metrics_to_dict(res.metrics))
    summary = {c: _summarize(rows) for c, rows in per_ctrl.items()}
    return {
        "n_runs": n_runs,
        "seed": seed,
        "base_scenario": base_scenario,
        "summary": summary,
        "runs": per_ctrl,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def col(key: str) -> np.ndarray:
        return np.array([r[key] for r in rows], dtype=float)

    out: dict[str, Any] = {}
    for key in (
        "methane_total_kg",
        "curtailment_fraction",
        "downtime_hours",
        "survival_score",
        "availability",
        "min_soc",
        "fault_production_ratio",
        "soh_loss",
    ):
        x = col(key)
        out[key] = {
            "mean": float(np.mean(x)),
            "p10": float(np.percentile(x, 10)),
            "p50": float(np.percentile(x, 50)),
            "p90": float(np.percentile(x, 90)),
        }
    rec = [r["recovery_hours"] for r in rows if r["recovery_hours"] is not None]
    recovered = sum(1 for r in rows if r["recovery_hours"] is not None or r["downtime_hours"] < 3)
    out["fault_recovery_rate"] = recovered / max(len(rows), 1)
    out["mean_recovery_hours"] = float(np.mean(rec)) if rec else None
    return out


def fault_test(fault_type: str, controller: str = "mpc", seed: int = 5) -> SimulationResult:
    cfg = load_scenario("baseline", controller, seed)
    cfg.name = f"fault_{fault_type}"
    cfg.faults.faults = [FaultSpec(type=fault_type, start_hour=48.0, severity=0.35)]
    if fault_type.startswith("sensor"):
        cfg.faults.faults[0].component = "hydrogen_flow"
        cfg.faults.faults[0].severity = 1.0
    return run_experiment(cfg)


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def default(o: Any) -> Any:
        if isinstance(o, SimulationResult):
            return o.to_serializable(thin=True)
        raise TypeError(type(o))

    # Drop heavy result objects if present
    payload = data
    if isinstance(data, dict) and "results" in data:
        payload = {k: v for k, v in data.items() if k != "results"}
        payload["metrics"] = data.get("controllers")
    path.write_text(json.dumps(payload, indent=2, default=default))


def write_csv_summary(monte: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["controller,metric,mean,p10,p50,p90"]
    for ctrl, stats in monte["summary"].items():
        for metric, vals in stats.items():
            if not isinstance(vals, dict) or "mean" not in vals:
                continue
            lines.append(
                f"{ctrl},{metric},{vals['mean']:.6f},{vals['p10']:.6f},{vals['p50']:.6f},{vals['p90']:.6f}"
            )
    path.write_text("\n".join(lines) + "\n")
