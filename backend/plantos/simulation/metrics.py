# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Plant Survival Score and run-level metrics.

The score answers: how well did the plant remain productive under adversity?
Weights are configurable and normalised. They are not a claim about the
physical world — they are a competition metric with an explicit rationale
in docs/EXPERIMENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import SurvivalScoreConfig
from plantos.plant.state import PlantState


@dataclass
class RunMetrics:
    methane_total_kg: float
    hydrogen_total_kg: float
    mean_methane_kgph: float
    curtailment_fraction: float
    mean_soc: float
    min_soc: float
    mean_soh: float
    soh_loss: float
    mean_el_health: float
    downtime_hours: float
    availability: float
    recovery_hours: float | None
    fault_production_ratio: float
    survival_score: float
    n_steps: int
    hours: float


def _curtailment_fraction(states: list[PlantState]) -> float:
    avail = sum(s.solar_available_mw for s in states)
    curt = sum(s.curtailed_power_mw for s in states)
    if avail <= 1e-6:
        return 0.0
    return float(np.clip(curt / avail, 0.0, 1.5))


def compute_metrics(
    states: list[PlantState],
    dt_hours: float,
    survival: SurvivalScoreConfig,
    reference_methane_kg: float | None = None,
    fault_hours: list[float] | None = None,
    nameplate_ch4_kgph: float = 320.0,
) -> RunMetrics:
    if not states:
        raise ValueError("No states to score")
    n = len(states)
    hours = n * dt_hours
    methane = states[-1].methane_total_kg
    hydrogen = states[-1].hydrogen_total_kg
    mean_ch4 = float(np.mean([s.methane_rate_kgph for s in states]))
    # Downtime: methane near zero while the plant is not simply in night idle
    # with full health. Use process load + methane.
    down = 0.0
    for s in states:
        # Downtime = solar energy was available but the process was not converting it.
        # Mode flags alone would reward a naive controller that never enters FAULT.
        if s.solar_available_mw > 1.5 and s.methane_rate_kgph < 5.0 and s.electrolyser_power_mw < 0.5:
            down += dt_hours
    availability = 1.0 - down / max(hours, dt_hours)

    # Recovery: hours from first FAULT/DEGRADED to return to NORMAL/RECOVERY with methane>10
    recovery = None
    in_fault = False
    t_fault = None
    for s in states:
        if s.plant_mode.value in {"FAULT", "DEGRADED", "EMERGENCY"} and not in_fault:
            in_fault = True
            t_fault = s.hour
        if in_fault and s.plant_mode.value in {"NORMAL", "RECOVERY"} and s.methane_rate_kgph > 10:
            recovery = s.hour - (t_fault or s.hour)
            in_fault = False

    soh_loss = states[0].battery_soh - states[-1].battery_soh
    mean_soh = float(np.mean([s.battery_soh for s in states]))
    mean_soc = float(np.mean([s.battery_soc for s in states]))
    min_soc = float(np.min([s.battery_soc for s in states]))
    mean_el_h = float(np.mean([s.electrolyser_health for s in states]))
    curt = _curtailment_fraction(states)

    # Fault tolerance: production during hours with active faults vs overall mean
    fault_mask = [1.0 if s.active_faults else 0.0 for s in states]
    if fault_hours:
        fault_mask = [1.0 if any(abs(s.hour - fh) < 0.51 for fh in fault_hours) or s.active_faults else 0.0 for s in states]
    if sum(fault_mask) > 0:
        prod_fault = np.mean([s.methane_rate_kgph for s, m in zip(states, fault_mask) if m])
        fault_ratio = float(prod_fault / max(mean_ch4, 1e-3))
    else:
        fault_ratio = 1.0

    ref = (
        reference_methane_kg
        if reference_methane_kg and reference_methane_kg > 1
        else 0.40 * nameplate_ch4_kgph * hours
    )
    prod_term = float(np.clip(methane / ref, 0.0, 1.3))
    rec_term = 1.0 if recovery is None else float(np.exp(-max(recovery, 0.0) / 8.0))
    if in_fault and recovery is None:
        rec_term = 0.15
    batt_term = float(np.clip((mean_soc - 0.10) / 0.50, 0.0, 1.0))
    health_term = float(np.clip((mean_el_h + mean_soh) / 2.0, 0.0, 1.0))
    curt_term = float(np.clip(1.0 - curt, 0.0, 1.0))
    fault_term = float(np.clip(fault_ratio, 0.0, 1.2))

    w = survival
    tw = w.production + w.availability + w.recovery_speed + w.curtailment + w.battery_reserve + w.equipment_health + w.fault_tolerance
    tw = tw or 1.0
    score = (
        w.production * prod_term
        + w.availability * availability
        + w.recovery_speed * rec_term
        + w.curtailment * curt_term
        + w.battery_reserve * batt_term
        + w.equipment_health * health_term
        + w.fault_tolerance * min(fault_term, 1.0)
    ) / tw
    score = float(np.clip(score, 0.0, 1.0))

    return RunMetrics(
        methane_total_kg=float(methane),
        hydrogen_total_kg=float(hydrogen),
        mean_methane_kgph=mean_ch4,
        curtailment_fraction=curt,
        mean_soc=mean_soc,
        min_soc=min_soc,
        mean_soh=mean_soh,
        soh_loss=float(soh_loss),
        mean_el_health=mean_el_h,
        downtime_hours=float(down),
        availability=float(availability),
        recovery_hours=None if recovery is None else float(recovery),
        fault_production_ratio=float(fault_ratio),
        survival_score=score,
        n_steps=n,
        hours=float(hours),
    )


def metrics_to_dict(m: RunMetrics) -> dict:
    return {
        "methane_total_kg": m.methane_total_kg,
        "hydrogen_total_kg": m.hydrogen_total_kg,
        "mean_methane_kgph": m.mean_methane_kgph,
        "curtailment_fraction": m.curtailment_fraction,
        "mean_soc": m.mean_soc,
        "min_soc": m.min_soc,
        "mean_soh": m.mean_soh,
        "soh_loss": m.soh_loss,
        "mean_el_health": m.mean_el_health,
        "downtime_hours": m.downtime_hours,
        "availability": m.availability,
        "recovery_hours": m.recovery_hours,
        "fault_production_ratio": m.fault_production_ratio,
        "survival_score": m.survival_score,
        "n_steps": m.n_steps,
        "hours": m.hours,
    }
