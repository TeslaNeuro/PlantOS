# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Physical constants and documented modelling assumptions.

Default plant ratings and simplified coefficients are listed in
``docs/ASSUMPTIONS.md``. Values here are SI-adjacent engineering units used
consistently across the simulator (MW, MWh, kg, °C, hours).
"""

from __future__ import annotations

# Hydrogen heating values (kWh/kg). Source: standard thermochemical values.
LHV_HYDROGEN_KWH_PER_KG = 33.33
HHV_HYDROGEN_KWH_PER_KG = 39.41

# Sabatier reaction (mass basis), CO2 + 4 H2 -> CH4 + 2 H2O
# 44.01 + 8.064 -> 16.04 + 36.03  (approx. 2.75 kg CO2 and 0.503 kg H2 per kg CH4)
H2_PER_CH4_KG = 8.064 / 16.04  # ≈ 0.5027 kg H2 / kg CH4
CO2_PER_CH4_KG = 44.01 / 16.04  # ≈ 2.744 kg CO2 / kg CH4
H2O_PER_CH4_KG = 36.03 / 16.04  # ≈ 2.246 kg H2O / kg CH4

# Standard PV test conditions
STC_IRRADIANCE_W_M2 = 1000.0
STC_TEMPERATURE_C = 25.0

# Numerical tolerances for physical invariant checks
ENERGY_TOLERANCE_MWH = 1e-6
MASS_TOLERANCE_KG = 1e-4
SOC_TOLERANCE = 1e-6
POWER_TOLERANCE_MW = 1e-6
