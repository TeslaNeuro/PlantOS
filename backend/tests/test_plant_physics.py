# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Phase 1 — plant physics and invariant tests."""

from __future__ import annotations

import numpy as np
import pytest

from plantos.config import BatteryConfig, ElectrolyserConfig, MethanationConfig, PlantConfig
from plantos.constants import CO2_PER_CH4_KG, H2_PER_CH4_KG, LHV_HYDROGEN_KWH_PER_KG
from plantos.plant.actions import ControlAction
from plantos.plant.battery import battery_energy_balance_holds, step_battery
from plantos.plant.electrolyser import hydrogen_from_power, step_electrolyser
from plantos.plant.invariants import InvariantError
from plantos.plant.methanation import step_methanation
from plantos.plant.plant import initial_state, step_plant
from plantos.plant.solar import available_solar_mw
from plantos.config import ElectrolyserStatus


def test_solar_zero_at_night():
    cfg = PlantConfig().solar
    assert available_solar_mw(0.0, 15.0, cfg) == 0.0


def test_solar_clips_at_capacity():
    cfg = PlantConfig().solar
    p = available_solar_mw(2000.0, 10.0, cfg)
    assert p <= cfg.capacity_mw + 1e-9


def test_solar_hot_day_derates():
    cfg = PlantConfig().solar
    cold = available_solar_mw(900.0, 5.0, cfg)
    hot = available_solar_mw(900.0, 40.0, cfg)
    assert hot < cold


def test_battery_energy_conservation_roundtrip():
    cfg = BatteryConfig()
    dt = 1.0
    # Charge 2 MW for 1 h then discharge the stored DC energy.
    charged = step_battery(0.5, 1.0, 25.0, -2.0, 25.0, dt, cfg)
    assert battery_energy_balance_holds(0.5, charged.soc, 1.0, charged.power_mw, dt, cfg)
    discharged = step_battery(charged.soc, charged.soh, charged.temperature_c, 2.0, 25.0, dt, cfg)
    assert battery_energy_balance_holds(charged.soc, discharged.soc, charged.soh, discharged.power_mw, dt, cfg)
    # Round-trip must lose energy: SOC after charge+discharge < original if same AC energy.
    # 2 MWh AC in * eta_ch stored, then 2 MWh AC out requires 2/eta_dis from storage.
    stored = 2.0 * cfg.charge_efficiency
    needed = 2.0 / cfg.discharge_efficiency
    assert needed > stored
    assert discharged.soc < 0.5 - 1e-6


def test_battery_respects_soc_limits():
    cfg = BatteryConfig()
    res = step_battery(cfg.soc_min, 1.0, 25.0, 6.0, 25.0, 1.0, cfg)
    assert res.soc >= cfg.soc_min - 1e-6
    res = step_battery(cfg.soc_max, 1.0, 25.0, -6.0, 25.0, 1.0, cfg)
    assert res.soc <= cfg.soc_max + 1e-6


def test_electrolyser_hydrogen_matches_specific_energy():
    cfg = ElectrolyserConfig()
    p = 8.0
    h2 = hydrogen_from_power(p, cfg, 1.0)
    # At rated load part-load factor is 1.0, so kWh/kg = nominal.
    assert h2 == pytest.approx((p * 1000.0) / cfg.nominal_kwh_per_kg, rel=1e-6)
    # LHV efficiency should be in a plausible electrolyser range (50–80%).
    eta = (h2 * LHV_HYDROGEN_KWH_PER_KG) / (p * 1000.0)
    assert 0.5 < eta < 0.8


def test_electrolyser_min_stable_and_ramp():
    cfg = ElectrolyserConfig()
    off = step_electrolyser(
        ElectrolyserStatus.OFF, 0.0, 8.0, True, 1.0, 25.0, 0.0, 20.0, 1.0, cfg
    )
    assert off.status == ElectrolyserStatus.STARTING
    running = step_electrolyser(
        ElectrolyserStatus.RUNNING, 2.0, 8.0, True, 1.0, 40.0, 1.0, 20.0, 1.0, cfg
    )
    assert running.power_mw <= 2.0 + cfg.ramp_mw_per_hour + 1e-9
    assert running.power_mw >= cfg.min_stable_power_mw - 1e-9 or running.power_mw == 0.0


def test_electrolyser_fault_stops_production():
    cfg = ElectrolyserConfig()
    res = step_electrolyser(
        ElectrolyserStatus.RUNNING,
        6.0,
        6.0,
        True,
        1.0,
        50.0,
        1.0,
        20.0,
        1.0,
        cfg,
        complete_fault=True,
    )
    # May still be ramping down this hour, but status is shutdown/fault/off.
    assert res.status in {
        ElectrolyserStatus.FAULT,
        ElectrolyserStatus.SHUTDOWN,
        ElectrolyserStatus.OFF,
    }


def test_methanation_mass_balance():
    cfg = MethanationConfig()
    res = step_methanation(
        load=0.8,
        commanded_load=0.8,
        temperature_c=300.0,
        warmup=1.0,
        health=1.0,
        h2_stored_kg=400.0,
        co2_stored_kg=1500.0,
        h2_in_kgph=0.0,
        co2_in_kgph=0.0,
        ambient_c=20.0,
        dt_hours=1.0,
        config=cfg,
    )
    if res.methane_kgph > 1e-6:
        assert res.h2_consumed_kgph == pytest.approx(res.methane_kgph * H2_PER_CH4_KG, rel=1e-6)
        assert res.co2_consumed_kgph == pytest.approx(res.methane_kgph * CO2_PER_CH4_KG, rel=1e-6)
    # Cannot exceed storage.
    assert res.h2_stored_kg >= -1e-6
    assert res.co2_stored_kg >= -1e-6


def test_methanation_cold_reactor_produces_nothing():
    cfg = MethanationConfig()
    res = step_methanation(
        0.0, 1.0, 25.0, 0.0, 1.0, 400.0, 1500.0, 100.0, 400.0, 20.0, 1.0, cfg
    )
    assert res.methane_kgph == 0.0
    assert res.load <= cfg.ramp_fraction_per_hour + 1e-9


def test_methanation_cannot_exceed_reactants():
    cfg = MethanationConfig()
    res = step_methanation(
        1.0, 1.0, 300.0, 1.0, 1.0, 0.5, 2.0, 0.0, 0.0, 20.0, 1.0, cfg
    )
    assert res.methane_kgph * H2_PER_CH4_KG <= 0.5 + 1e-6
    assert res.methane_kgph * CO2_PER_CH4_KG <= 2.0 + 1e-6


def test_plant_step_power_and_invariants():
    cfg = PlantConfig()
    state = initial_state(cfg)
    action = ControlAction(
        electrolyser_power_mw=3.0,
        co2_capture_power_mw=0.8,
        methanation_load=0.5,
        battery_power_mw=0.0,
        electrolyser_run=True,
    )
    nxt, trace = step_plant(state, action, 800.0, 22.0, 0.1, 1.0, cfg, check=True)
    assert nxt.solar_power_mw > 0
    assert 0 <= nxt.battery_soc <= 1
    supply = trace.solar_delivered_mw + trace.battery_discharge_mw
    demand = (
        trace.battery_charge_mw
        + trace.electrolyser_mw
        + trace.co2_mw
        + trace.methanation_mw
        + trace.auxiliary_mw
        + max(trace.residual_mw, 0.0)
    )
    assert supply == pytest.approx(demand, abs=5e-3)


def test_no_energy_from_nowhere_dark_idle():
    cfg = PlantConfig()
    state = initial_state(cfg)
    soc0 = state.battery_soc
    action = ControlAction()
    nxt, _ = step_plant(state, action, 0.0, 10.0, 1.0, 1.0, cfg, check=True)
    assert nxt.solar_power_mw == 0.0
    # Idle still draws auxiliary from the battery.
    assert nxt.battery_soc <= soc0 + 1e-9
    assert nxt.methane_rate_kgph == 0.0
