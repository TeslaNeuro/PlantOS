"""FastAPI control-room backend. Simulation logic is independent of the UI."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from plantos.config import FaultSpec
from plantos.experiments.runner import (
    compare_controllers,
    load_scenario,
    monte_carlo,
    simulate,
)
from plantos.simulation.engine import SimulationResult, run_experiment

app = FastAPI(title="PlantOS", version="0.1.0", description="Autonomous operations API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STORE: dict[str, dict[str, Any]] = {}
_LATEST: str | None = None


class RunRequest(BaseModel):
    scenario: str = "storm"
    controller: str = "mpc"
    seed: int | None = None


class CompareRequest(BaseModel):
    scenario: str = "storm"
    seed: int | None = None


class MonteCarloRequest(BaseModel):
    runs: int = Field(20, ge=2, le=200)
    scenario: str = "baseline"
    seed: int = 123


class FaultInjectRequest(BaseModel):
    type: str = "electrolyser_efficiency"
    start_hour: float = 48
    severity: float = 0.35
    component: str | None = None
    scenario: str = "baseline"
    controller: str = "mpc"
    seed: int = 5


def _store(payload: dict[str, Any]) -> str:
    global _LATEST
    rid = str(uuid4())[:8]
    _STORE[rid] = payload
    _LATEST = rid
    return rid


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "plantos"}


@app.post("/simulation/run")
def simulation_run(req: RunRequest) -> dict[str, Any]:
    res = simulate(req.scenario, req.controller, req.seed)
    payload = res.to_serializable(thin=False)
    rid = _store(payload)
    payload["id"] = rid
    return payload


@app.post("/simulation/compare")
def simulation_compare(req: CompareRequest) -> dict[str, Any]:
    cmp = compare_controllers(req.scenario, req.seed)
    # Attach thin timeseries for the dashboard playback of MPC vs others.
    results: dict[str, SimulationResult] = cmp.pop("results")
    payload = {
        "scenario": cmp["scenario"],
        "seed": cmp["seed"],
        "controllers": cmp["controllers"],
        "events": cmp["events"],
        "timeseries": {k: r.to_serializable(thin=True)["timeseries"] for k, r in results.items()},
        "weather": results["mpc"].to_serializable(thin=True)["weather"],
        "full_events": {k: [e.to_dict() for e in r.events] for k, r in results.items()},
        "counterfactual": {
            "without": cmp["controllers"]["naive"],
            "with": cmp["controllers"]["mpc"],
            "methane_saved_kg": results["mpc"].metrics.methane_total_kg - results["naive"].metrics.methane_total_kg,
            "downtime_avoided_hours": results["naive"].metrics.downtime_hours - results["mpc"].metrics.downtime_hours,
        },
    }
    rid = _store(payload)
    payload["id"] = rid
    return payload


@app.post("/simulation/monte-carlo")
def simulation_mc(req: MonteCarloRequest) -> dict[str, Any]:
    mc = monte_carlo(n_runs=req.runs, base_scenario=req.scenario, seed=req.seed)
    rid = _store(mc)
    mc["id"] = rid
    return mc


@app.post("/fault/inject")
def fault_inject(req: FaultInjectRequest) -> dict[str, Any]:
    cfg = load_scenario(req.scenario, req.controller, req.seed)
    cfg.faults.faults = [
        FaultSpec(type=req.type, start_hour=req.start_hour, severity=req.severity, component=req.component)
    ]
    res = run_experiment(cfg)
    payload = res.to_serializable(thin=False)
    rid = _store(payload)
    payload["id"] = rid
    return payload


@app.get("/plant/state")
def plant_state(hour: float | None = None, result_id: str | None = None) -> dict[str, Any]:
    payload = _get(result_id)
    series = payload.get("timeseries") or payload.get("steps")
    if not series:
        raise HTTPException(404, "No timeseries in stored result")
    if isinstance(series, dict):
        series = series.get("mpc") or next(iter(series.values()))
    if hour is None:
        return series[-1]
    idx = min(max(int(hour), 0), len(series) - 1)
    return series[idx]


@app.get("/plant/events")
def plant_events(result_id: str | None = None) -> dict[str, Any]:
    payload = _get(result_id)
    return {"events": payload.get("events") or payload.get("full_events", {}).get("mpc", [])}


@app.get("/results/{result_id}")
def get_results(result_id: str) -> dict[str, Any]:
    return _get(result_id)


@app.get("/results")
def list_results() -> dict[str, Any]:
    return {"ids": list(_STORE.keys()), "latest": _LATEST}


def _get(result_id: str | None) -> dict[str, Any]:
    rid = result_id or _LATEST
    if rid is None or rid not in _STORE:
        raise HTTPException(404, "No simulation result. Run POST /simulation/run first.")
    return _STORE[rid]
