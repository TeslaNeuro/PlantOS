# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Li-ion battery with SOC, SOH and a simplified degradation model.

Energy balance (charge positive into the battery):

    E_nom_eff = E_nom * SOH
    ΔE_ac     = P_batt * dt          # P_batt > 0 discharge to plant
    if discharging:
        SOC += - (P_dis * dt) / (η_dis * E_nom_eff)
    if charging:
        SOC +=   (η_ch * P_ch * dt) / E_nom_eff

Round-trip efficiency is η_ch * η_dis. Energy that fails the efficiency
conversion is treated as heat, not as a free lunch.

Degradation (documented default): throughput cycling plus a mild calendar
and temperature/SOC stress term. This is not a full SEI/rainflow model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import BatteryConfig
from plantos.constants import ENERGY_TOLERANCE_MWH, SOC_TOLERANCE


@dataclass
class BatteryStepResult:
    soc: float
    soh: float
    power_mw: float  # +discharge, -charge, after clipping
    throughput_mwh: float
    temperature_c: float
    energy_ac_mwh: float
    energy_dc_mwh: float
    clipped: bool


def usable_capacity_mwh(config: BatteryConfig, soh: float) -> float:
    return config.energy_capacity_mwh * max(soh, 0.05)


def available_battery_power(
    soc: float,
    soh: float,
    dt_hours: float,
    config: BatteryConfig,
    capacity_derate: float = 1.0,
    loss_multiplier: float = 1.0,
) -> tuple[float, float]:
    """Return (max_discharge_mw, max_charge_mw) feasible this step."""
    e_nom = usable_capacity_mwh(config, soh) * float(np.clip(capacity_derate, 0.05, 1.0))
    eta_ch = float(np.clip(config.charge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))
    eta_dis = float(np.clip(config.discharge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))
    energy_to_full = max(config.soc_max - soc, 0.0) * e_nom
    energy_to_empty = max(soc - config.soc_min, 0.0) * e_nom
    max_charge = min(config.max_charge_mw, energy_to_full / max(eta_ch * dt_hours, 1e-12))
    max_discharge = min(config.max_discharge_mw, energy_to_empty * eta_dis / max(dt_hours, 1e-12))
    return float(max(max_discharge, 0.0)), float(max(max_charge, 0.0))


def step_battery(
    soc: float,
    soh: float,
    temperature_c: float,
    commanded_power_mw: float,
    ambient_c: float,
    dt_hours: float,
    config: BatteryConfig,
    capacity_derate: float = 1.0,
    loss_multiplier: float = 1.0,
    thermal_fault: float = 0.0,
) -> BatteryStepResult:
    """Advance battery one step.

    commanded_power_mw: +discharge (to plant), -charge (from plant).
    capacity_derate: fault-induced reduction of usable energy (0-1 remaining).
    loss_multiplier: >1 increases internal losses (fault).
    """
    e_nom = usable_capacity_mwh(config, soh) * float(np.clip(capacity_derate, 0.05, 1.0))
    p_cmd = float(commanded_power_mw)

    eta_ch = float(np.clip(config.charge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))
    eta_dis = float(np.clip(config.discharge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))

    max_ch = config.max_charge_mw
    max_dis = config.max_discharge_mw

    # Headroom in AC-equivalent power for this timestep.
    energy_to_full = max(config.soc_max - soc, 0.0) * e_nom
    energy_to_empty = max(soc - config.soc_min, 0.0) * e_nom
    max_charge_now = min(max_ch, energy_to_full / max(eta_ch * dt_hours, 1e-12))
    max_discharge_now = min(max_dis, energy_to_empty * eta_dis / max(dt_hours, 1e-12))

    clipped = False
    if p_cmd >= 0:
        p = min(p_cmd, max_discharge_now)
        if p < p_cmd - 1e-12:
            clipped = True
        energy_ac = p * dt_hours
        energy_dc = energy_ac / eta_dis if p > 0 else 0.0
        soc_next = soc - energy_dc / e_nom
    else:
        p_ch = min(-p_cmd, max_charge_now)
        if p_ch < -p_cmd - 1e-12:
            clipped = True
        p = -p_ch
        energy_ac = -p_ch * dt_hours
        energy_dc = -p_ch * eta_ch * dt_hours
        soc_next = soc + (-energy_dc) / e_nom  # energy_dc negative when charging? keep signed AC

        # Recompute SOC from charged DC energy (positive into battery).
        soc_next = soc + (p_ch * eta_ch * dt_hours) / e_nom
        energy_dc = p_ch * eta_ch * dt_hours

    soc_next = float(np.clip(soc_next, config.soc_min - SOC_TOLERANCE, config.soc_max + SOC_TOLERANCE))
    soc_next = float(np.clip(soc_next, 0.0, 1.0))

    throughput = abs(p) * dt_hours
    # Temperature: simple RC toward ambient plus I²R-like heat from throughput.
    heat = 0.6 * abs(p) + 8.0 * thermal_fault
    temp_next = temperature_c + dt_hours * (0.15 * (ambient_c - temperature_c) + 0.35 * heat)
    temp_next = float(np.clip(temp_next, -10.0, 70.0))

    temp_stress = 1.0 + config.temp_degradation_coeff * max(temp_next - 25.0, 0.0)
    soc_stress = 1.0 + config.high_soc_stress * max(soc_next - 0.8, 0.0)
    cycle_loss = config.cycle_degradation_per_mwh * throughput * temp_stress * soc_stress
    calendar_loss = config.calendar_degradation_per_hour * dt_hours * temp_stress
    soh_next = float(np.clip(soh - cycle_loss - calendar_loss, 0.4, 1.0))

    return BatteryStepResult(
        soc=soc_next,
        soh=soh_next,
        power_mw=p,
        throughput_mwh=throughput,
        temperature_c=temp_next,
        energy_ac_mwh=energy_ac if p_cmd >= 0 else -p_ch * dt_hours,
        energy_dc_mwh=energy_dc if p_cmd >= 0 else p_ch * eta_ch * dt_hours,
        clipped=clipped,
    )


def battery_energy_balance_holds(
    soc_before: float,
    soc_after: float,
    soh: float,
    power_mw: float,
    dt_hours: float,
    config: BatteryConfig,
    capacity_derate: float = 1.0,
    loss_multiplier: float = 1.0,
) -> bool:
    """Check that SOC movement matches efficiency-adjusted energy."""
    e_nom = usable_capacity_mwh(config, soh) * float(np.clip(capacity_derate, 0.05, 1.0))
    eta_ch = float(np.clip(config.charge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))
    eta_dis = float(np.clip(config.discharge_efficiency / max(loss_multiplier, 1.0), 0.5, 1.0))
    if power_mw >= 0:
        expected = soc_before - (power_mw * dt_hours) / (eta_dis * e_nom)
    else:
        expected = soc_before + ((-power_mw) * eta_ch * dt_hours) / e_nom
    return abs(expected - soc_after) <= 5e-4 + ENERGY_TOLERANCE_MWH / max(e_nom, 1e-6)
