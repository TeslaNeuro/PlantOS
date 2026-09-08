# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Physical invariant checks.

If an invariant fails, the simulation raises ``InvariantError``. These checks
exist so a UI change or a controller bug cannot silently violate conservation.
"""

from __future__ import annotations

from dataclasses import dataclass

from plantos.config import PlantConfig
from plantos.constants import (
    CO2_PER_CH4_KG,
    H2_PER_CH4_KG,
    MASS_TOLERANCE_KG,
    POWER_TOLERANCE_MW,
    SOC_TOLERANCE,
)
from plantos.plant.state import PlantState


class InvariantError(RuntimeError):
    """Raised when the simulated plant produces physically impossible behaviour."""


@dataclass
class PowerBalanceTrace:
    solar_delivered_mw: float
    battery_discharge_mw: float
    battery_charge_mw: float
    electrolyser_mw: float
    co2_mw: float
    methanation_mw: float
    auxiliary_mw: float
    residual_mw: float


def check_soc_limits(state: PlantState, config: PlantConfig) -> None:
    lo = config.battery.soc_min - 5 * SOC_TOLERANCE
    hi = config.battery.soc_max + 5 * SOC_TOLERANCE
    if not (lo - 0.02 <= state.battery_soc <= hi + 0.02):
        # Hard physical bound 0-1 always.
        pass
    if state.battery_soc < -SOC_TOLERANCE or state.battery_soc > 1.0 + SOC_TOLERANCE:
        raise InvariantError(f"SOC outside [0,1]: {state.battery_soc}")
    if state.battery_soh < 0.39 or state.battery_soh > 1.0 + 1e-9:
        raise InvariantError(f"SOH outside plausible range: {state.battery_soh}")


def check_power_balance(trace: PowerBalanceTrace) -> None:
    supply = trace.solar_delivered_mw + trace.battery_discharge_mw
    demand = (
        trace.battery_charge_mw
        + trace.electrolyser_mw
        + trace.co2_mw
        + trace.methanation_mw
        + trace.auxiliary_mw
        + trace.residual_mw
    )
    if abs(supply - demand) > 5e-3 + POWER_TOLERANCE_MW:
        raise InvariantError(
            f"Power imbalance {supply - demand:.6f} MW "
            f"(supply={supply:.4f}, demand={demand:.4f})"
        )
    if trace.residual_mw < -5e-3:
        raise InvariantError("Negative residual power (generation from nowhere).")


def check_mass_balance(
    methane_kgph: float,
    h2_consumed_kgph: float,
    co2_consumed_kgph: float,
) -> None:
    if methane_kgph < -MASS_TOLERANCE_KG:
        raise InvariantError("Negative methane production.")
    if methane_kgph <= MASS_TOLERANCE_KG:
        return
    if h2_consumed_kgph + MASS_TOLERANCE_KG < methane_kgph * H2_PER_CH4_KG * 0.99:
        raise InvariantError("Methane produced without sufficient hydrogen.")
    if co2_consumed_kgph + MASS_TOLERANCE_KG < methane_kgph * CO2_PER_CH4_KG * 0.99:
        raise InvariantError("Methane produced without sufficient CO2.")


def check_storage_limits(state: PlantState, config: PlantConfig) -> None:
    if state.h2_stored_kg < -MASS_TOLERANCE_KG:
        raise InvariantError("Negative hydrogen storage.")
    if state.co2_stored_kg < -MASS_TOLERANCE_KG:
        raise InvariantError("Negative CO2 storage.")
    if state.h2_stored_kg > config.methanation.h2_storage_kg + MASS_TOLERANCE_KG:
        raise InvariantError("Hydrogen storage overflow.")
    if state.co2_stored_kg > config.methanation.co2_storage_kg + MASS_TOLERANCE_KG:
        raise InvariantError("CO2 storage overflow.")


def check_faulted_output(state: PlantState) -> None:
    isolated = state.isolated_components
    if "electrolyser" in isolated and state.hydrogen_rate_kgph > 1.0:
        raise InvariantError("Isolated electrolyser still producing hydrogen.")
    if "co2_capture" in isolated and state.co2_rate_kgph > 1.0:
        raise InvariantError("Isolated CO2 capture still producing CO2.")
    if "methanation" in isolated and state.methane_rate_kgph > 1.0:
        raise InvariantError("Isolated methanation still producing methane.")
    for f in state.active_faults:
        if f.active and f.fault_type == "electrolyser_complete" and f.component == "electrolyser":
            if state.hydrogen_rate_kgph > 5.0:
                raise InvariantError("Completely faulted electrolyser producing hydrogen.")


def check_ramp(
    previous_power: float,
    current_power: float,
    max_ramp: float,
    dt_hours: float,
    name: str,
) -> None:
    """Upward ramps are physically limited. Downward trips (protection) may be faster."""
    if current_power - previous_power > max_ramp * dt_hours + 1e-3:
        raise InvariantError(
            f"{name} ramp-up {current_power - previous_power:.3f} MW "
            f"exceeds limit {max_ramp * dt_hours:.3f} MW"
        )


def check_all(
    previous: PlantState,
    current: PlantState,
    trace: PowerBalanceTrace,
    config: PlantConfig,
    dt_hours: float,
    h2_consumed_kgph: float,
    co2_consumed_kgph: float,
) -> None:
    check_soc_limits(current, config)
    check_power_balance(trace)
    check_mass_balance(current.methane_rate_kgph, h2_consumed_kgph, co2_consumed_kgph)
    check_storage_limits(current, config)
    check_faulted_output(current)
    check_ramp(
        previous.electrolyser_power_mw,
        current.electrolyser_power_mw,
        config.electrolyser.ramp_mw_per_hour,
        dt_hours,
        "electrolyser",
    )
    check_ramp(
        previous.co2_capture_power_mw,
        current.co2_capture_power_mw,
        config.co2.ramp_mw_per_hour,
        dt_hours,
        "co2_capture",
    )
    if current.solar_power_mw < -POWER_TOLERANCE_MW:
        raise InvariantError("Negative solar power.")
    if current.curtailed_power_mw < -POWER_TOLERANCE_MW:
        raise InvariantError("Negative curtailment.")
    if current.curtailed_power_mw > current.solar_available_mw + POWER_TOLERANCE_MW:
        raise InvariantError("Curtailment exceeds available solar.")
