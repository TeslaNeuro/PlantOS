"""Catalytic methanation (Sabatier) with thermal inertia and mass-balance limits.

Stoichiometry (mass):

    0.503 kg H2 + 2.744 kg CO2  ->  1.0 kg CH4  +  2.25 kg H2O

The reactor cannot jump to a new conversion instantly. A first-order lag on
load and a thermal state enforce startup delay and ramp limits:

    load(t+1) = load(t) + clip(u - load, ±ramp)
    T(t+1)    = T + (T_op - T)/τ * dt * f(load) - loss*(T - T_amb) + reaction heat

Methane is produced only when T exceeds T_min. Production is the minimum of
commanded conversion, available H2, available CO2, and thermal capability.

Simplification: no spatial reactor profile, no recycle compressor map.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import MethanationConfig
from plantos.constants import CO2_PER_CH4_KG, H2_PER_CH4_KG


@dataclass
class MethanationStepResult:
    load: float
    power_mw: float
    methane_kgph: float
    h2_consumed_kgph: float
    co2_consumed_kgph: float
    temperature_c: float
    warmup: float
    health: float
    h2_stored_kg: float
    co2_stored_kg: float


def conversion_available(temperature_c: float, config: MethanationConfig) -> float:
    """0 below min temperature, 1 at operating temperature (smoothstep)."""
    t0 = config.min_temperature_c
    t1 = config.operating_temperature_c
    if temperature_c <= t0:
        return 0.0
    if temperature_c >= t1:
        return 1.0
    x = (temperature_c - t0) / (t1 - t0)
    return x * x * (3.0 - 2.0 * x)


def step_methanation(
    load: float,
    commanded_load: float,
    temperature_c: float,
    warmup: float,
    health: float,
    h2_stored_kg: float,
    co2_stored_kg: float,
    h2_in_kgph: float,
    co2_in_kgph: float,
    ambient_c: float,
    dt_hours: float,
    config: MethanationConfig,
    isolated: bool = False,
    throughput_fault: float = 0.0,
    thermal_fault: float = 0.0,
    emergency_shed: bool = False,
) -> MethanationStepResult:
    h2_store = min(h2_stored_kg + h2_in_kgph * dt_hours, config.h2_storage_kg)
    co2_store = min(co2_stored_kg + co2_in_kgph * dt_hours, config.co2_storage_kg)

    if isolated or emergency_shed:
        commanded_load = 0.0

    u = float(np.clip(commanded_load, 0.0, 1.0))
    if 0 < u < config.min_load_fraction:
        u = 0.0 if u < 0.5 * config.min_load_fraction else config.min_load_fraction

    max_delta = 1.0 if emergency_shed else config.ramp_fraction_per_hour * dt_hours
    load_next = load + float(np.clip(u - load, -max_delta, max_delta))
    load_next = float(np.clip(load_next, 0.0, 1.0))

    warmup_next = warmup
    if load_next > 0.05:
        warmup_next = min(1.0, warmup + dt_hours / max(config.startup_delay_hours, 1e-9))
    else:
        warmup_next = max(0.0, warmup - 0.5 * dt_hours / max(config.startup_delay_hours, 1e-9))

    # Thermal dynamics.
    target = config.operating_temperature_c if load_next > 0.05 else ambient_c
    tau = config.thermal_time_constant_h
    dT = (target - temperature_c) / max(tau, 0.2)
    dT += config.reaction_heat_gain * load_next
    dT -= config.ambient_heat_loss * (temperature_c - ambient_c) / 100.0
    dT += 25.0 * thermal_fault
    temp_next = float(np.clip(temperature_c + dT * dt_hours, ambient_c - 2.0, config.max_temperature_c))

    conv = conversion_available(temp_next, config) * warmup_next * health * (1.0 - throughput_fault)
    cap = config.max_ch4_kg_per_h * conv * load_next

    h2_avail = h2_store / max(dt_hours, 1e-9)
    co2_avail = co2_store / max(dt_hours, 1e-9)
    ch4_from_h2 = h2_avail / H2_PER_CH4_KG
    ch4_from_co2 = co2_avail / CO2_PER_CH4_KG
    methane = min(cap, ch4_from_h2, ch4_from_co2) * config.conversion_efficiency
    methane = max(methane, 0.0)

    h2_use = methane * H2_PER_CH4_KG
    co2_use = methane * CO2_PER_CH4_KG
    h2_store = max(h2_store - h2_use * dt_hours, 0.0)
    co2_store = max(co2_store - co2_use * dt_hours, 0.0)

    power = methane * config.aux_kwh_per_kg / 1000.0  # MW
    health_next = float(
        np.clip(
            health
            - 3e-6 * load_next * dt_hours
            - 8e-6 * max(temp_next - config.operating_temperature_c, 0.0) * dt_hours,
            0.4,
            1.0,
        )
    )

    return MethanationStepResult(
        load=load_next,
        power_mw=power,
        methane_kgph=methane,
        h2_consumed_kgph=h2_use,
        co2_consumed_kgph=co2_use,
        temperature_c=temp_next,
        warmup=warmup_next,
        health=health_next,
        h2_stored_kg=h2_store,
        co2_stored_kg=co2_store,
    )
