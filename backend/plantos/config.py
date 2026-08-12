"""Typed configuration for plant, sensors, controller, simulation and experiments.

Every experiment must bind a complete configuration plus a random seed so that
results are reproducible. Invented numeric parameters are flagged in
``docs/ASSUMPTIONS.md``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ControllerType(str, Enum):
    NAIVE = "naive"
    RULES = "rules"
    MPC = "mpc"


class PlantMode(str, Enum):
    NORMAL = "NORMAL"
    FORECAST_UNCERTAIN = "FORECAST_UNCERTAIN"
    POWER_CONSTRAINED = "POWER_CONSTRAINED"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"
    EMERGENCY = "EMERGENCY"
    RECOVERY = "RECOVERY"


class ElectrolyserStatus(str, Enum):
    OFF = "OFF"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"
    SHUTDOWN = "SHUTDOWN"


class SolarConfig(BaseModel):
    """STC-rated PV array with a linear temperature derate and inverter clip."""

    capacity_mw: float = 12.0
    derate: float = Field(0.86, description="Soiling, mismatch, wiring, inverter (not cell efficiency).")
    temp_coeff_per_c: float = Field(-0.004, description="Power temperature coefficient (1/°C).")
    noct_c: float = Field(45.0, description="Nominal Operating Cell Temperature.")


class BatteryConfig(BaseModel):
    energy_capacity_mwh: float = 24.0
    max_charge_mw: float = 6.0
    max_discharge_mw: float = 6.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.95
    initial_soc: float = 0.55
    initial_soh: float = 1.0
    # Degradation (invented, order-of-magnitude Li-ion). See ASSUMPTIONS.md.
    cycle_degradation_per_mwh: float = 2.5e-5
    calendar_degradation_per_hour: float = 1.5e-6
    temp_degradation_coeff: float = 0.04
    high_soc_stress: float = 0.3


class ElectrolyserConfig(BaseModel):
    max_power_mw: float = 8.0
    min_stable_power_mw: float = 1.6
    nominal_kwh_per_kg: float = Field(50.0, description="System specific energy at rated load (LHV basis ~66.7%).")
    ramp_mw_per_hour: float = 4.0
    startup_hours: float = 1.0
    shutdown_hours: float = 1.0
    startup_energy_mwh: float = 0.4
    initial_health: float = 1.0
    thermal_mass: float = 8.0
    heat_per_mw: float = 2.5
    cooling_coeff: float = 0.35
    max_temperature_c: float = 80.0
    degradation_per_mwh: float = 8e-6
    thermal_degradation_coeff: float = 1.2e-5


class CO2CaptureConfig(BaseModel):
    """Remote-plant DAC-like capture. Specific energy is an optimistic solid-sorbent value."""

    max_power_mw: float = 2.2
    min_power_mw: float = 0.3
    kwh_per_kg: float = 2.0
    capture_efficiency: float = 0.90
    ramp_mw_per_hour: float = 1.5
    initial_health: float = 1.0
    max_throughput_kg_per_h: float = 1000.0


class MethanationConfig(BaseModel):
    max_ch4_kg_per_h: float = 320.0
    min_load_fraction: float = 0.25
    ramp_fraction_per_hour: float = 0.40
    startup_delay_hours: float = 2.0
    aux_kwh_per_kg: float = 0.25
    conversion_efficiency: float = 0.97
    thermal_time_constant_h: float = 2.0
    min_temperature_c: float = 220.0
    operating_temperature_c: float = 300.0
    max_temperature_c: float = 450.0
    ambient_heat_loss: float = 0.15
    reaction_heat_gain: float = 0.8
    initial_health: float = 1.0
    h2_storage_kg: float = 800.0
    co2_storage_kg: float = 2500.0
    initial_h2_kg: float = 120.0
    initial_co2_kg: float = 400.0


class ThermalAmbientConfig(BaseModel):
    """Shared thermal environment. Equipment models add their own heat balances."""

    initial_temperature_c: float = 25.0


class PlantConfig(BaseModel):
    name: str = "PlantOS-PtG-1"
    solar: SolarConfig = Field(default_factory=SolarConfig)
    battery: BatteryConfig = Field(default_factory=BatteryConfig)
    electrolyser: ElectrolyserConfig = Field(default_factory=ElectrolyserConfig)
    co2: CO2CaptureConfig = Field(default_factory=CO2CaptureConfig)
    methanation: MethanationConfig = Field(default_factory=MethanationConfig)
    thermal: ThermalAmbientConfig = Field(default_factory=ThermalAmbientConfig)
    auxiliary_mw: float = 0.08


class SensorChannelConfig(BaseModel):
    noise_std: float = 0.0
    bias: float = 0.0
    drift_per_hour: float = 0.0
    fail_probability: float = 0.0


class SensorConfig(BaseModel):
    solar_power: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.04)
    )
    battery_soc: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.008)
    )
    battery_power: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.03)
    )
    electrolyser_power: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.04)
    )
    hydrogen_flow: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=1.5)
    )
    co2_flow: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=4.0)
    )
    methane_flow: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=2.0)
    )
    electrolyser_temperature: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.4)
    )
    methanation_temperature: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.8)
    )
    co2_power: SensorChannelConfig = Field(
        default_factory=lambda: SensorChannelConfig(noise_std=0.02)
    )


class ForecastConfig(BaseModel):
    bias_wm2: float = 20.0
    noise_std_wm2: float = 60.0
    ar1_phi: float = 0.72
    temp_bias_c: float = 0.4
    temp_noise_std_c: float = 1.2
    failure_probability: float = 0.0
    failure_start_hour: float | None = None
    failure_duration_hours: float = 6.0
    horizon_hours: int = 48


class WeatherConfig(BaseModel):
    latitude_deg: float = 50.0
    start_day_of_year: int = 172  # late June, long European days
    scenario: str = "mixed"
    source: str = Field("synthetic", description="'synthetic' or 'external'")
    external_path: str | None = None


class FaultSpec(BaseModel):
    type: str
    start_hour: float
    end_hour: float | None = None
    severity: float = 0.3
    component: str | None = None


class FaultConfig(BaseModel):
    faults: list[FaultSpec] = Field(default_factory=list)


class MPCObjectiveConfig(BaseModel):
    methane_weight: float = 12.0
    curtailment_penalty: float = 4.0
    degradation_penalty: float = 8.0
    startup_penalty: float = 25.0
    shutdown_penalty: float = 10.0
    battery_stress_penalty: float = 3.5
    downtime_penalty: float = 40.0
    risk_penalty: float = 15.0
    reserve_penalty: float = 30.0
    soc_reserve: float = 0.25
    horizon_hours: int = 48


class RuleControllerConfig(BaseModel):
    soc_reserve: float = 0.22
    soc_high: float = 0.85
    min_run_hours: float = 2.0
    poor_weather_wm2: float = 180.0
    look_ahead_hours: int = 6
    scarcity_soc: float = 0.35


class SurvivalScoreConfig(BaseModel):
    """Weights must be non-negative. They are normalised at evaluation time."""

    production: float = 0.28
    availability: float = 0.16
    recovery_speed: float = 0.14
    curtailment: float = 0.10
    battery_reserve: float = 0.10
    equipment_health: float = 0.12
    fault_tolerance: float = 0.10


class SimulationConfig(BaseModel):
    dt_hours: float = 1.0
    horizon_hours: int = 240  # 10 days
    seed: int = 42
    check_invariants: bool = True


class ExperimentConfig(BaseModel):
    name: str = "default"
    plant: PlantConfig = Field(default_factory=PlantConfig)
    sensors: SensorConfig = Field(default_factory=SensorConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    faults: FaultConfig = Field(default_factory=FaultConfig)
    mpc: MPCObjectiveConfig = Field(default_factory=MPCObjectiveConfig)
    rules: RuleControllerConfig = Field(default_factory=RuleControllerConfig)
    survival: SurvivalScoreConfig = Field(default_factory=SurvivalScoreConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    controller: ControllerType = ControllerType.MPC

    @field_validator("controller", mode="before")
    @classmethod
    def _coerce_controller(cls, value: Any) -> Any:
        if isinstance(value, str):
            return ControllerType(value.lower())
        return value


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return ExperimentConfig.model_validate(raw)


def dump_experiment_config(config: ExperimentConfig, path: str | Path) -> None:
    Path(path).write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
