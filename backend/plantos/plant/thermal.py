"""Shared first-order thermal helper.

    T(t+dt) = T + dt * (heat_generation - cooling_coeff * (T - T_amb)) / thermal_mass

Used by documentation and tests; equipment modules inline specialised versions.
"""

from __future__ import annotations

import numpy as np


def step_temperature(
    temperature_c: float,
    ambient_c: float,
    heat_generation: float,
    cooling_coeff: float,
    thermal_mass: float,
    dt_hours: float,
    t_min: float | None = None,
    t_max: float | None = None,
) -> float:
    dT = (heat_generation - cooling_coeff * (temperature_c - ambient_c)) / max(thermal_mass, 1e-9)
    t = temperature_c + dT * dt_hours
    if t_min is not None:
        t = max(t, t_min)
    if t_max is not None:
        t = min(t, t_max)
    return float(t)


def thermal_limit_exceeded(temperature_c: float, limit_c: float, margin_c: float = 0.0) -> bool:
    return temperature_c > limit_c + margin_c + 1e-9
