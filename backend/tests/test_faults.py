"""Fault injection, detection, diagnosis and mode transitions."""

from __future__ import annotations

from plantos.config import ExperimentConfig, FaultConfig, FaultSpec, SensorConfig
from plantos.estimation.sensors import SensorBank
from plantos.faults.detection import FaultDetector
from plantos.faults.engine import FaultEngine
from plantos.plant.actions import ControlAction
from plantos.plant.plant import AppliedFaults, initial_state, step_plant
from plantos.plant.state import PlantState


def test_electrolyser_efficiency_fault_reduces_hydrogen():
    cfg = ExperimentConfig().plant
    state = initial_state(cfg)
    # Warm up to running.
    action = ControlAction(electrolyser_power_mw=6.0, electrolyser_run=True, methanation_load=0.0)
    for _ in range(3):
        state, _ = step_plant(state, action, 900.0, 20.0, 0.1, 1.0, cfg, check=True)
    healthy_h2 = state.hydrogen_rate_kgph
    faults = AppliedFaults(el_efficiency=0.35)
    state2, _ = step_plant(state, action, 900.0, 20.0, 0.1, 1.0, cfg, faults=faults, check=True)
    assert state2.hydrogen_rate_kgph < healthy_h2 * 0.9


def test_fault_engine_applies_at_start_hour():
    fc = FaultConfig(faults=[FaultSpec(type="solar_shading", start_hour=10, severity=0.3)])
    eng = FaultEngine(fc)
    sensors = SensorBank(SensorConfig(), 0)
    state = PlantState()
    af, _, recs = eng.apply(9.0, state, sensors)
    assert recs == []
    assert af.solar_shading == 1.0
    af, _, recs = eng.apply(10.0, state, sensors)
    assert recs and recs[0].fault_type == "solar_shading"
    assert abs(af.solar_shading - 0.7) < 1e-9


def test_complete_electrolyser_fault_cannot_sustain_output():
    cfg = ExperimentConfig().plant
    state = initial_state(cfg)
    action = ControlAction(electrolyser_power_mw=6.0, electrolyser_run=True)
    for _ in range(3):
        state, _ = step_plant(state, action, 900.0, 20.0, 0.1, 1.0, cfg)
    faults = AppliedFaults(el_complete=True)
    for _ in range(4):
        state, _ = step_plant(state, action, 900.0, 20.0, 0.1, 1.0, cfg, faults=faults)
    assert state.hydrogen_rate_kgph < 5.0


def test_detector_flags_efficiency_loss():
    cfg = ExperimentConfig().plant
    det = FaultDetector(cfg, persist_hours=1.0)
    from plantos.estimation.kalman import EstimatedState
    from plantos.estimation.sensors import Measurement

    belief = EstimatedState(
        hour=50,
        solar_power_mw=6.0,
        battery_soc=0.5,
        battery_soh=1.0,
        battery_power_mw=0.0,
        electrolyser_power_mw=6.0,
        electrolyser_health=1.0,
        electrolyser_temperature_c=50.0,
        hydrogen_rate_kgph=120.0,
        co2_capture_power_mw=1.0,
        co2_capture_health=1.0,
        co2_rate_kgph=400.0,
        methanation_power_mw=0.05,
        methanation_health=1.0,
        methanation_temperature_c=300.0,
        methane_rate_kgph=200.0,
        h2_stored_kg=100.0,
        co2_stored_kg=400.0,
        plant_load_mw=7.0,
        soc_uncertainty=0.01,
        forecast_uncertainty=0.2,
        electrolyser_status="RUNNING",
    )
    # Healthy yield ~ 6e3/50 = 120 kg/h. Faulted yield much lower.
    meas = Measurement(
        hour=50,
        values={
            "solar_power": 6.0,
            "battery_soc": 0.5,
            "battery_power": 0.0,
            "electrolyser_power": 6.0,
            "hydrogen_flow": 70.0,
            "co2_flow": 400.0,
            "methane_flow": 200.0,
            "electrolyser_temperature": 50.0,
            "methanation_temperature": 300.0,
            "co2_power": 1.0,
        },
    )
    out = None
    for _ in range(3):
        out = det.update(belief, meas, 800.0, 20.0, 1.0)
    assert out is not None
    assert out.fault_type in {"electrolyser_efficiency", "electrolyser_partial", "electrolyser_complete"}
    assert out.residuals.efficiency_pp < -5
