# Assumptions

Every invented or simplified parameter is listed here. Do not treat these as measured plant data.

## Scope of the physics

The plant is a **lumped hourly (or 15-minute) model** of a remote power-to-methane site. It is not a CFD reactor, not a full PV I–V curve, and not a battery electrochemical model.

## Solar PV

| Parameter | Default | Origin |
|---|---|---|
| Capacity | 12 MW | Invented, order-of-magnitude PtG |
| Derate | 0.86 | Typical soiling/mismatch/inverter |
| Temperature coefficient | −0.004 /°C | Typical c-Si |
| NOCT | 45 °C | Typical module |
| Clear-sky GHI | Haurwitz-like | Simplified, not REST2 |
| Cloud attenuation | Kasten–Czeplak style | Simplified |

## Battery

| Parameter | Default | Origin |
|---|---|---|
| Energy | 24 MWh | Invented |
| Charge/discharge | 6 MW | Invented |
| η_ch, η_dis | 0.95 | Typical Li-ion power conversion |
| SOC band | 10–95% | Invented operating policy |
| Cycle degradation | 2.5×10⁻⁵ / MWh | Invented order-of-magnitude |
| Calendar degradation | 1.5×10⁻⁶ / h | Invented |

Round-trip efficiency is η_ch × η_dis. Lost energy is heat, not free electricity.

## Electrolyser

| Parameter | Default | Origin |
|---|---|---|
| Rated power | 8 MW | Invented |
| Min stable | 1.6 MW (20%) | PEM-like |
| Specific energy | 50 kWh/kg | ~66.7% LHV; optimistic system value |
| Ramp | 4 MW/h | Hourly-resolution stand-in for faster real PEM |
| Startup | 1 h + 0.4 MWh | Coarse; real PEM can be faster |
| Part-load curve | 0.90 + 0.16x − 0.06x² | Invented BOP penalty |

Hydrogen LHV = 33.33 kWh/kg (standard).

## CO₂ capture

Modelled as electrically driven DAC-like supply for a remote site (no pipeline).

| Parameter | Default | Origin |
|---|---|---|
| Specific energy | 2.0 kWh/kg | Optimistic solid-sorbent electrical equivalent |
| Capture efficiency | 0.90 | Invented lumped factor |
| Max power | 2.2 MW | Sized to methanation |

This does **not** resolve adsorbent beds, vacuum pumps or thermal regeneration.

## Methanation (Sabatier)

Mass stoichiometry (standard molar masses):

- 0.503 kg H₂ + 2.744 kg CO₂ → 1.0 kg CH₄ + 2.25 kg H₂O

| Parameter | Default | Origin |
|---|---|---|
| Max CH₄ | 320 kg/h | Matches ~8 MW electrolysis |
| Conversion | 0.97 | Invented |
| Thermal time constant | 2 h | Invented first-order lag |
| Min temperature | 220 °C | Order-of-magnitude Ni catalyst |
| Aux power | 0.25 kWh/kg | Compressors/BOP, invented |

The reactor cannot jump to a new conversion instantly. That is deliberate.

## Weather

Synthetic 50°N late-June geometry. Not a reanalysis product. External CSV can be loaded later; the core has **no API dependency**.

## Forecast

Bias, AR(1) noise and optional clear-sky failure. These are **not** NWP verification statistics.

## Sensors / estimator

Gaussian noise, bias, drift, freeze, fail. Decoupled Kalman filters — not a full EKF of the hybrid plant.

## Fault detection

Residual thresholds and persistence hours are invented. Hypothesis scores are **heuristic likelihoods**, not calibrated probabilities.

## MPC

Linear relaxation of commitment. Thermal states are not in the LP. Simultaneous charge/discharge is penalised, not forbidden with binaries. Horizon 24–48 h.

## Survival score

A configurable weighted index, not a physical observable. Production is scored against 40% of nameplate methanation over the run, not against the run’s own output (which would make every controller score 1.0 on production).

## What this prototype is not

- Not a certified safety system
- Not a substitute for IEC 61850 / SIL protection
- Not trained on real plant data
- Not a claim that PlantOS has been deployed
