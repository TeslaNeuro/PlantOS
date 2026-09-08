# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""CO2 capture / DAC-like supply.

Remote islanded plants in this model do not have a pipeline CO2 source. Capture is
modelled as an electrically driven unit:

    m_co2 = (P_mw * 1000 * capture_efficiency * health) / kwh_per_kg

capped by max_throughput. This is a lumped model: it does not resolve
adsorbent beds, vacuum pumps or thermal regeneration separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import CO2CaptureConfig


@dataclass
class CO2StepResult:
    power_mw: float
    co2_kgph: float
    health: float


def step_co2_capture(
    power_mw: float,
    commanded_power_mw: float,
    health: float,
    dt_hours: float,
    config: CO2CaptureConfig,
    isolated: bool = False,
    capacity_fault: float = 0.0,
    complete_fault: bool = False,
    emergency_shed: bool = False,
) -> CO2StepResult:
    health_next = float(np.clip(health - 1.5e-6 * max(power_mw, 0.0) * dt_hours, 0.4, 1.0))
    if isolated or complete_fault:
        p = max(power_mw - config.ramp_mw_per_hour * dt_hours, 0.0)
        return CO2StepResult(power_mw=p if p > 1e-6 else 0.0, co2_kgph=0.0, health=health_next)

    p_max = config.max_power_mw * health * (1.0 - capacity_fault)
    p_cmd = float(np.clip(commanded_power_mw, 0.0, p_max))
    if 0 < p_cmd < config.min_power_mw:
        p_cmd = 0.0

    delta = p_cmd - power_mw
    max_up = config.ramp_mw_per_hour * dt_hours
    max_down = power_mw if emergency_shed else max_up
    p = power_mw + float(np.clip(delta, -max_down, max_up))
    p = float(np.clip(p, 0.0, p_max))

    if p < 0.5 * config.min_power_mw:
        p = 0.0
        co2 = 0.0
    else:
        co2 = (p * 1000.0) / config.kwh_per_kg * config.capture_efficiency * health * (1.0 - 0.5 * capacity_fault)
        co2 = min(co2, config.max_throughput_kg_per_h * (1.0 - capacity_fault))

    return CO2StepResult(power_mw=p, co2_kgph=max(co2, 0.0), health=health_next)
