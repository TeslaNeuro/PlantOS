# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Plant reality: one physics step given actuator commands and exogenous weather.

This module is the only place that advances true plant state. Controllers must
not call it with future information; the simulator loop enforces that split.

Power is allocated *before* equipment is stepped so the islanded bus cannot
create energy. Equipment setpoints are clipped to solar + feasible discharge.
"""

from __future__ import annotations

from dataclasses import dataclass

from plantos.config import PlantConfig
from plantos.plant.actions import ControlAction
from plantos.plant.battery import available_battery_power, step_battery
from plantos.plant.co2 import step_co2_capture
from plantos.plant.electrolyser import step_electrolyser
from plantos.plant.invariants import PowerBalanceTrace, check_all
from plantos.plant.methanation import step_methanation
from plantos.plant.solar import available_solar_mw
from plantos.plant.state import PlantState


@dataclass
class AppliedFaults:
    solar_shading: float = 1.0
    battery_capacity: float = 1.0
    battery_loss: float = 1.0
    battery_thermal: float = 0.0
    el_efficiency: float = 0.0
    el_partial: float = 0.0
    el_complete: bool = False
    co2_capacity: float = 0.0
    co2_complete: bool = False
    meth_throughput: float = 0.0
    meth_thermal: float = 0.0


def initial_state(config: PlantConfig) -> PlantState:
    return PlantState(
        battery_soc=config.battery.initial_soc,
        battery_soh=config.battery.initial_soh,
        electrolyser_health=config.electrolyser.initial_health,
        co2_capture_health=config.co2.initial_health,
        methanation_health=config.methanation.initial_health,
        h2_stored_kg=config.methanation.initial_h2_kg,
        co2_stored_kg=config.methanation.initial_co2_kg,
        battery_temp_c=config.thermal.initial_temperature_c,
        electrolyser_temperature_c=config.thermal.initial_temperature_c,
        methanation_temperature_c=config.thermal.initial_temperature_c,
        available_capacity={
            "solar": 1.0,
            "battery": 1.0,
            "electrolyser": 1.0,
            "co2_capture": 1.0,
            "methanation": 1.0,
        },
    )


def _clip_commands_to_budget(
    el_cmd: float,
    co2_cmd: float,
    meth_aux_mw: float,
    auxiliary_mw: float,
    budget_mw: float,
) -> tuple[float, float, float]:
    """Scale flexible loads so el + co2 + meth_aux + aux <= budget."""
    aux = max(auxiliary_mw, 0.0)
    flexible = max(el_cmd, 0.0) + max(co2_cmd, 0.0) + max(meth_aux_mw, 0.0)
    remaining = budget_mw - aux
    if remaining <= 0:
        return 0.0, 0.0, 0.0
    if flexible <= remaining + 1e-12:
        return max(el_cmd, 0.0), max(co2_cmd, 0.0), max(meth_aux_mw, 0.0)
    scale = remaining / flexible
    return max(el_cmd, 0.0) * scale, max(co2_cmd, 0.0) * scale, max(meth_aux_mw, 0.0) * scale


def _predict_power(current: float, cmd: float, ramp: float, dt: float, emergency: bool) -> float:
    up = ramp * dt
    down = current if emergency else up
    return max(current + max(min(cmd - current, up), -down), 0.0)


def step_plant(
    state: PlantState,
    action: ControlAction,
    irradiance_wm2: float,
    ambient_c: float,
    cloud_cover: float,
    dt_hours: float,
    config: PlantConfig,
    faults: AppliedFaults | None = None,
    check: bool = True,
) -> tuple[PlantState, PowerBalanceTrace]:
    faults = faults or AppliedFaults()
    nxt = state.copy()
    nxt.hour = state.hour + dt_hours
    nxt.timestamp_hour = nxt.hour
    nxt.irradiance_wm2 = irradiance_wm2
    nxt.ambient_temp_c = ambient_c
    nxt.cloud_cover = cloud_cover

    isolated = set(state.isolated_components) | set(action.isolate)
    isolated -= set(action.recover)
    nxt.isolated_components = isolated

    available = available_solar_mw(
        irradiance_wm2, ambient_c, config.solar, shading_factor=faults.solar_shading
    )
    # Operator curtailment reduces the solar that may be used.
    available_after_op_curtail = max(available - max(action.curtailment_mw, 0.0), 0.0)
    op_curtail = available - available_after_op_curtail

    max_dis, max_ch = available_battery_power(
        state.battery_soc,
        state.battery_soh,
        dt_hours,
        config.battery,
        capacity_derate=faults.battery_capacity,
        loss_multiplier=faults.battery_loss,
    )
    power_budget = max(available_after_op_curtail + max_dis, 0.0)
    aux_served = min(config.auxiliary_mw, power_budget)
    power_budget = max(power_budget - 0.02, 0.0)

    # Island protection: if the bus cannot support process load, trip it.
    # Controllers may over-commit from a wrong SOC estimate; physics must not.
    scarce = power_budget < aux_served + 0.25

    # Methanation aux is small and load-dependent; budget a conservative cap.
    meth_aux_req = 0.0 if scarce else min(
        action.methanation_load * config.methanation.max_ch4_kg_per_h * config.methanation.aux_kwh_per_kg / 1000.0,
        0.2,
    )
    el_cmd, co2_cmd, _ = _clip_commands_to_budget(
        0.0 if scarce else action.electrolyser_power_mw,
        0.0 if scarce else action.co2_capture_power_mw,
        meth_aux_req,
        aux_served,
        power_budget,
    )
    emergency_shed = scarce
    for _ in range(8):
        el_pred = _predict_power(
            state.electrolyser_power_mw, el_cmd, config.electrolyser.ramp_mw_per_hour, dt_hours, emergency_shed
        )
        co2_pred = _predict_power(
            state.co2_capture_power_mw, co2_cmd, config.co2.ramp_mw_per_hour, dt_hours, emergency_shed
        )
        predicted = el_pred + co2_pred + meth_aux_req + aux_served
        if predicted <= power_budget + 1e-4:
            break
        emergency_shed = True
        overflow = predicted - power_budget + 1e-3
        if el_cmd > 0:
            cut = min(el_cmd, overflow)
            el_cmd -= cut
            overflow -= cut
        if overflow > 0:
            co2_cmd = max(0.0, co2_cmd - overflow)
            el_cmd = 0.0
    if 0 < el_cmd < config.electrolyser.min_stable_power_mw:
        el_cmd = 0.0
        emergency_shed = True
    if 0 < co2_cmd < config.co2.min_power_mw:
        co2_cmd = 0.0
        emergency_shed = True

    el = step_electrolyser(
        status=state.electrolyser_status,
        power_mw=state.electrolyser_power_mw,
        commanded_power_mw=el_cmd,
        run_command=action.electrolyser_run and "electrolyser" not in isolated and el_cmd > 0.05,
        health=state.electrolyser_health,
        temperature_c=state.electrolyser_temperature_c,
        startup_progress=state.electrolyser_startup_progress,
        ambient_c=ambient_c,
        dt_hours=dt_hours,
        config=config.electrolyser,
        isolated="electrolyser" in isolated,
        efficiency_fault=faults.el_efficiency,
        partial_fault=faults.el_partial,
        complete_fault=faults.el_complete,
        emergency_shed=emergency_shed,
    )
    co2 = step_co2_capture(
        power_mw=state.co2_capture_power_mw,
        commanded_power_mw=co2_cmd,
        health=state.co2_capture_health,
        dt_hours=dt_hours,
        config=config.co2,
        isolated="co2_capture" in isolated,
        capacity_fault=faults.co2_capacity,
        complete_fault=faults.co2_complete,
        emergency_shed=emergency_shed,
    )
    meth = step_methanation(
        load=state.methanation_load,
        commanded_load=0.0 if scarce else (action.methanation_load if power_budget > aux_served else 0.0),
        temperature_c=state.methanation_temperature_c,
        warmup=state.methanation_warmup,
        health=state.methanation_health,
        h2_stored_kg=state.h2_stored_kg,
        co2_stored_kg=state.co2_stored_kg,
        h2_in_kgph=el.hydrogen_kgph,
        co2_in_kgph=co2.co2_kgph,
        ambient_c=ambient_c,
        dt_hours=dt_hours,
        config=config.methanation,
        isolated="methanation" in isolated,
        throughput_fault=faults.meth_throughput,
        thermal_fault=faults.meth_thermal,
        emergency_shed=emergency_shed or scarce,
    )

    load_mw = el.power_mw + co2.power_mw + meth.power_mw + aux_served
    if load_mw > available_after_op_curtail + max_dis + 1e-3:
        # Second-pass protection: trip process load to what the bus can actually serve.
        el = step_electrolyser(
            status=state.electrolyser_status,
            power_mw=state.electrolyser_power_mw,
            commanded_power_mw=0.0,
            run_command=False,
            health=state.electrolyser_health,
            temperature_c=state.electrolyser_temperature_c,
            startup_progress=state.electrolyser_startup_progress,
            ambient_c=ambient_c,
            dt_hours=dt_hours,
            config=config.electrolyser,
            isolated=True,
            efficiency_fault=faults.el_efficiency,
            partial_fault=faults.el_partial,
            complete_fault=faults.el_complete,
            emergency_shed=True,
        )
        co2 = step_co2_capture(
            power_mw=state.co2_capture_power_mw,
            commanded_power_mw=0.0,
            health=state.co2_capture_health,
            dt_hours=dt_hours,
            config=config.co2,
            isolated=True,
            capacity_fault=faults.co2_capacity,
            complete_fault=faults.co2_complete,
            emergency_shed=True,
        )
        meth = step_methanation(
            load=state.methanation_load,
            commanded_load=0.0,
            temperature_c=state.methanation_temperature_c,
            warmup=state.methanation_warmup,
            health=state.methanation_health,
            h2_stored_kg=state.h2_stored_kg,
            co2_stored_kg=state.co2_stored_kg,
            h2_in_kgph=el.hydrogen_kgph,
            co2_in_kgph=co2.co2_kgph,
            ambient_c=ambient_c,
            dt_hours=dt_hours,
            config=config.methanation,
            isolated=True,
            throughput_fault=faults.meth_throughput,
            thermal_fault=faults.meth_thermal,
            emergency_shed=True,
        )
        aux_served = min(config.auxiliary_mw, available_after_op_curtail + max_dis)
        load_mw = el.power_mw + co2.power_mw + meth.power_mw + aux_served

    # Islanded battery dispatch: p_batt = load - solar_used, +discharge / -charge.
    # Feasible solar_used in [max(0, load - max_dis), min(available_after_op_curtail, load + max_ch)].
    solar_min = max(0.0, load_mw - max_dis)
    solar_max = min(available_after_op_curtail, load_mw + max_ch)

    if abs(action.battery_power_mw) < 1e-12:
        # Auto: use solar first, charge surplus, discharge deficit.
        solar_used = min(max(load_mw, solar_min), solar_max) if solar_max >= solar_min else solar_min
        if available_after_op_curtail > load_mw:
            solar_used = min(available_after_op_curtail, load_mw + max_ch)
    else:
        # p_batt requested: solar_used = load - p_batt
        solar_used = load_mw - action.battery_power_mw
        solar_used = min(max(solar_used, solar_min), solar_max)

    if solar_max < solar_min - 1e-6:
        # Blackout: not enough solar+battery for even the committed load.
        # Equipment already stepped; cover what we can and record shortfall.
        solar_used = min(available_after_op_curtail, load_mw)
        p_batt_cmd = load_mw - solar_used
    else:
        p_batt_cmd = load_mw - solar_used

    batt = step_battery(
        soc=state.battery_soc,
        soh=state.battery_soh,
        temperature_c=state.battery_temp_c,
        commanded_power_mw=p_batt_cmd,
        ambient_c=ambient_c,
        dt_hours=dt_hours,
        config=config.battery,
        capacity_derate=faults.battery_capacity,
        loss_multiplier=faults.battery_loss,
        thermal_fault=faults.battery_thermal,
    )

    discharge = max(batt.power_mw, 0.0)
    charge = max(-batt.power_mw, 0.0)
    solar_used = min(max(load_mw + charge - discharge, 0.0), available)
    extra_curtail = available - solar_used
    nxt.solar_available_mw = available
    nxt.solar_power_mw = solar_used
    nxt.curtailed_power_mw = extra_curtail

    nxt.battery_soc = batt.soc
    nxt.battery_soh = batt.soh
    nxt.battery_power_mw = batt.power_mw
    nxt.battery_throughput_mwh = state.battery_throughput_mwh + batt.throughput_mwh
    nxt.battery_temp_c = batt.temperature_c

    nxt.electrolyser_power_mw = el.power_mw
    nxt.electrolyser_health = el.health
    nxt.electrolyser_temperature_c = el.temperature_c
    nxt.electrolyser_status = el.status
    nxt.electrolyser_startup_progress = el.startup_progress
    nxt.hydrogen_rate_kgph = el.hydrogen_kgph

    nxt.co2_capture_power_mw = co2.power_mw
    nxt.co2_capture_health = co2.health
    nxt.co2_rate_kgph = co2.co2_kgph

    nxt.methanation_load = meth.load
    nxt.methanation_power_mw = meth.power_mw
    nxt.methanation_health = meth.health
    nxt.methanation_temperature_c = meth.temperature_c
    nxt.methane_rate_kgph = meth.methane_kgph
    nxt.methanation_warmup = meth.warmup
    nxt.h2_stored_kg = meth.h2_stored_kg
    nxt.co2_stored_kg = meth.co2_stored_kg
    nxt.methane_total_kg = state.methane_total_kg + meth.methane_kgph * dt_hours
    nxt.hydrogen_total_kg = state.hydrogen_total_kg + el.hydrogen_kgph * dt_hours
    nxt.co2_total_kg = state.co2_total_kg + co2.co2_kgph * dt_hours
    nxt.plant_load_mw = load_mw
    nxt.plant_mode = state.plant_mode
    nxt.active_faults = list(state.active_faults)
    nxt.available_capacity = {
        "solar": faults.solar_shading,
        "battery": faults.battery_capacity,
        "electrolyser": (1.0 - faults.el_partial) * (0.0 if faults.el_complete else 1.0),
        "co2_capture": (1.0 - faults.co2_capacity) * (0.0 if faults.co2_complete else 1.0),
        "methanation": 1.0 - faults.meth_throughput,
    }

    supply = nxt.solar_power_mw + discharge
    demand = charge + load_mw
    residual = supply - demand
    if residual > 1e-6:
        nxt.curtailed_power_mw += residual
        residual = 0.0
    elif residual > -5e-3:
        residual = 0.0

    trace = PowerBalanceTrace(
        solar_delivered_mw=nxt.solar_power_mw,
        battery_discharge_mw=discharge,
        battery_charge_mw=charge,
        electrolyser_mw=el.power_mw,
        co2_mw=co2.power_mw,
        methanation_mw=meth.power_mw,
        auxiliary_mw=aux_served,
        residual_mw=residual,
    )
    _ = op_curtail

    if check:
        check_all(
            state,
            nxt,
            trace,
            config,
            dt_hours,
            meth.h2_consumed_kgph,
            meth.co2_consumed_kgph,
        )

    return nxt, trace


def allocate_power(
    solar_mw: float,
    battery_discharge_available_mw: float,
    requested: dict[str, float],
    auxiliary_mw: float,
) -> dict[str, float]:
    """Greedy power allocator used by simple controllers. Never over-allocates."""
    remaining = solar_mw + battery_discharge_available_mw - auxiliary_mw
    remaining = max(remaining, 0.0)
    out: dict[str, float] = {k: 0.0 for k in requested}
    for key, req in requested.items():
        take = min(max(req, 0.0), remaining)
        out[key] = take
        remaining -= take
    out["unallocated"] = remaining
    return out
