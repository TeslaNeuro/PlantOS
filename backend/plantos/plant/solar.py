# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Photovoltaic generation.

Model (standard engineering approximation, not a full optical/electrical cell model):

    T_cell = T_amb + (NOCT - 20) / 800 * G
    P_dc   = P_stc * (G / 1000) * (1 + γ (T_cell - 25)) * derate
    P_ac   = clip(P_dc, 0, P_stc)     # inverter / plant clipping

Curtailment is a control action applied after available power is computed.
Partial shading and other solar faults are applied by the fault engine as a
multiplicative derate on available power.
"""

from __future__ import annotations

import numpy as np

from plantos.config import SolarConfig
from plantos.constants import STC_IRRADIANCE_W_M2, STC_TEMPERATURE_C


def cell_temperature_c(ambient_c: float, irradiance_wm2: float, noct_c: float) -> float:
    return ambient_c + (noct_c - 20.0) / 800.0 * max(irradiance_wm2, 0.0)


def available_solar_mw(
    irradiance_wm2: float,
    ambient_c: float,
    config: SolarConfig,
    shading_factor: float = 1.0,
) -> float:
    """AC-equivalent available PV power before operator curtailment."""
    g = max(float(irradiance_wm2), 0.0)
    t_cell = cell_temperature_c(ambient_c, g, config.noct_c)
    temp_factor = 1.0 + config.temp_coeff_per_c * (t_cell - STC_TEMPERATURE_C)
    p = (
        config.capacity_mw
        * (g / STC_IRRADIANCE_W_M2)
        * temp_factor
        * config.derate
        * float(np.clip(shading_factor, 0.0, 1.0))
    )
    return float(np.clip(p, 0.0, config.capacity_mw))


def apply_curtailment(available_mw: float, curtail_mw: float) -> tuple[float, float]:
    """Return (delivered_mw, actual_curtailed_mw)."""
    curtail = float(np.clip(curtail_mw, 0.0, max(available_mw, 0.0)))
    delivered = max(available_mw - curtail, 0.0)
    return delivered, curtail
