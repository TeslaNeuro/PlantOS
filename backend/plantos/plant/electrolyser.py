# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""PEM-style electrolyser with a load-dependent efficiency curve and a state machine.

Hydrogen production (kg/h):

    η(p) = η_nom * f(p / P_max)
    m_h2 = (P_mw * 1000 * η(p)) / LHV_H2     equivalently P / specific_energy

The specific energy at rated load is a configuration parameter (default 50 kWh/kg,
≈ 66.7% LHV). A mild convex curve makes part-load slightly worse, which is a
reasonable alkaline/PEM system-level approximation including BOP.

States: OFF, STARTING, RUNNING, DEGRADED, FAULT, SHUTDOWN.

Simplification: startup and shutdown complete in integer hours at the simulation
timestep. Sub-hour dynamics are not resolved.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import ElectrolyserConfig, ElectrolyserStatus
from plantos.constants import LHV_HYDROGEN_KWH_PER_KG


@dataclass
class ElectrolyserStepResult:
    power_mw: float
    hydrogen_kgph: float
    health: float
    temperature_c: float
    status: ElectrolyserStatus
    startup_progress: float
    specific_energy_kwh_per_kg: float


def part_load_factor(load_fraction: float) -> float:
    """Relative efficiency vs rated. Slightly worse at low load (system BOP)."""
    x = float(np.clip(load_fraction, 0.0, 1.0))
    # 0.88 at min-ish load, 1.0 at rated, 0.97 at very low.
    return 0.90 + 0.16 * x - 0.06 * x * x


def specific_energy_kwh_per_kg(power_mw: float, config: ElectrolyserConfig, health: float) -> float:
    if power_mw <= 1e-9:
        return config.nominal_kwh_per_kg
    load = power_mw / max(config.max_power_mw, 1e-9)
    # Health < 1 increases specific energy (more kWh per kg).
    health_factor = 1.0 / max(health, 0.2)
    return config.nominal_kwh_per_kg / part_load_factor(load) * health_factor


def _limited_power(current: float, target: float, ramp_mw_per_hour: float, dt_hours: float, emergency_shed: bool) -> float:
    max_up = ramp_mw_per_hour * dt_hours
    max_down = current if emergency_shed else max_up
    return float(np.clip(current + np.clip(target - current, -max_down, max_up), 0.0, None))


def hydrogen_from_power(power_mw: float, config: ElectrolyserConfig, health: float) -> float:
    if power_mw <= 1e-9:
        return 0.0
    kwh = specific_energy_kwh_per_kg(power_mw, config, health)
    return (power_mw * 1000.0) / kwh


def step_electrolyser(
    status: ElectrolyserStatus,
    power_mw: float,
    commanded_power_mw: float,
    run_command: bool,
    health: float,
    temperature_c: float,
    startup_progress: float,
    ambient_c: float,
    dt_hours: float,
    config: ElectrolyserConfig,
    isolated: bool = False,
    efficiency_fault: float = 0.0,
    partial_fault: float = 0.0,
    complete_fault: bool = False,
    emergency_shed: bool = False,
) -> ElectrolyserStepResult:
    """Advance electrolyser state machine and physics."""
    health_eff = float(np.clip(health * (1.0 - efficiency_fault), 0.2, 1.0))
    p_max = config.max_power_mw * health_eff * (1.0 - partial_fault)
    p_min = min(config.min_stable_power_mw, p_max)

    if isolated or complete_fault:
        target_status = ElectrolyserStatus.FAULT if complete_fault and not isolated else ElectrolyserStatus.OFF
        if isolated:
            target_status = ElectrolyserStatus.OFF
        p_next = _limited_power(
            power_mw, 0.0, config.ramp_mw_per_hour, dt_hours, emergency_shed or isolated or complete_fault
        )
        if p_next <= 1e-6:
            p_next = 0.0
            status_next = target_status
            progress = 0.0
            h2 = 0.0
        else:
            status_next = ElectrolyserStatus.SHUTDOWN
            progress = startup_progress
            h2 = 0.0
        temp = _thermal(temperature_c, ambient_c, p_next, dt_hours, config)
        health_next = _degrade(health, p_next, temp, dt_hours, config)
        return ElectrolyserStepResult(
            p_next, h2, health_next, temp, status_next, progress, specific_energy_kwh_per_kg(p_next, config, health_eff)
        )

    status_next = status
    progress = startup_progress
    p_cmd = float(np.clip(commanded_power_mw, 0.0, p_max))

    if status in {ElectrolyserStatus.OFF, ElectrolyserStatus.FAULT}:
        if run_command and p_cmd >= p_min * 0.5:
            status_next = ElectrolyserStatus.STARTING
            progress = 0.0
            target = min(p_cmd, config.startup_energy_mwh / max(dt_hours, 1e-9), p_max)
            p_next = _limited_power(power_mw, target, config.ramp_mw_per_hour, dt_hours, emergency_shed)
            h2 = 0.0
        else:
            p_next = 0.0
            h2 = 0.0
            status_next = ElectrolyserStatus.OFF
    elif status == ElectrolyserStatus.STARTING:
        progress = startup_progress + dt_hours / max(config.startup_hours, 1e-9)
        p_next = _limited_power(power_mw, min(max(p_cmd, 0.1), p_max), config.ramp_mw_per_hour, dt_hours, emergency_shed)
        h2 = 0.15 * hydrogen_from_power(p_next, config, health_eff)  # purge / ramp, little product
        if progress >= 1.0:
            status_next = ElectrolyserStatus.RUNNING
            progress = 1.0
            h2 = hydrogen_from_power(p_next, config, health_eff)
        elif not run_command:
            status_next = ElectrolyserStatus.SHUTDOWN
    elif status == ElectrolyserStatus.SHUTDOWN:
        p_next = _limited_power(power_mw, 0.0, config.ramp_mw_per_hour, dt_hours, emergency_shed)
        h2 = hydrogen_from_power(p_next, config, health_eff) * 0.3
        if p_next <= 1e-6:
            p_next = 0.0
            h2 = 0.0
            status_next = ElectrolyserStatus.OFF
            progress = 0.0
        elif run_command:
            status_next = ElectrolyserStatus.STARTING
    else:
        # RUNNING or DEGRADED
        if not run_command or p_cmd < 0.05:
            status_next = ElectrolyserStatus.SHUTDOWN
            target = 0.0
            p_next = _limited_power(power_mw, target, config.ramp_mw_per_hour, dt_hours, emergency_shed)
            h2 = hydrogen_from_power(p_next, config, health_eff) * 0.5
        else:
            if p_cmd + 1e-9 < p_min:
                status_next = ElectrolyserStatus.SHUTDOWN
                p_next = _limited_power(power_mw, 0.0, config.ramp_mw_per_hour, dt_hours, True)
                h2 = hydrogen_from_power(p_next, config, health_eff) * 0.5
            else:
                p_target = float(np.clip(p_cmd, min(p_min, p_max), p_max))
                p_next = _limited_power(power_mw, p_target, config.ramp_mw_per_hour, dt_hours, emergency_shed)
                p_next = float(np.clip(p_next, 0.0, p_max))
                h2 = hydrogen_from_power(p_next, config, health_eff)
                if health_eff < 0.85 or efficiency_fault > 0.15 or partial_fault > 0.15:
                    status_next = ElectrolyserStatus.DEGRADED
                else:
                    status_next = ElectrolyserStatus.RUNNING

    temp = _thermal(temperature_c, ambient_c, p_next, dt_hours, config)
    health_next = _degrade(health, p_next, temp, dt_hours, config)
    se = specific_energy_kwh_per_kg(p_next, config, health_eff)
    return ElectrolyserStepResult(
        power_mw=p_next,
        hydrogen_kgph=max(h2, 0.0),
        health=health_next,
        temperature_c=temp,
        status=status_next,
        startup_progress=progress,
        specific_energy_kwh_per_kg=se,
    )


def _thermal(temp: float, ambient: float, power: float, dt: float, config: ElectrolyserConfig) -> float:
    # T(t+1) = T + heating - cooling. Documented first-order approximation.
    dT = (config.heat_per_mw * power - config.cooling_coeff * (temp - ambient)) / max(config.thermal_mass, 1e-6)
    return float(np.clip(temp + dT * dt, ambient - 5.0, config.max_temperature_c + 15.0))


def _degrade(health: float, power: float, temp: float, dt: float, config: ElectrolyserConfig) -> float:
    thermal = max(temp - 50.0, 0.0) * config.thermal_degradation_coeff
    cycle = config.degradation_per_mwh * power * dt
    return float(np.clip(health - (cycle + thermal) * dt, 0.3, 1.0))
