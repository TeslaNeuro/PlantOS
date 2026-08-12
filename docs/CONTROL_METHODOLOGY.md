# Control methodology

## Naive

If estimated solar > 0.25 MW, allocate all of it to the electrolyser then CO₂ capture, and set methanation load high. No forecast, no reserve, no isolation, no recovery.

This is a straw-man “run when the sun is up” policy. It under-uses the battery and restarts the stack every morning, so methane is low and curtailment is high. That is expected.

## Rules

Deterministic policy:

- Keep a SOC reserve (raised when the reconfigurator is uncertain).
- Do not start the stack if the next 6 h of forecast PV is poor, unless already running.
- Honour a minimum run time of 2 h while SOC stays above reserve.
- Shed load when SOC is scarce.
- Apply isolation/recovery from the PlantOS reconfigurator (partial autonomy).

## MPC (PlantOS)

Receding horizon, default 24–48 hourly steps.

**Decision variables (per hour):** stack power, capture power, charge, discharge, curtailment, methane rate, SOC slack.

**Linear dynamics:** SOC, H₂ storage, CO₂ storage.

**Hard constraints:** SOC band, power limits, ramp-up, storage limits, available forecast PV, isolated/derated capacity.

**Objective (maximise):**

```
w_CH4 * methane
− w_curt * curtailment
− w_deg * battery throughput
− w_res * reserve slack
− small startup / risk terms
```

Only the first hour is applied. The LP is rebuilt every step from **belief + forecast**.

### Simplifications

- On/off commitment is relaxed. Minimum load is enforced when the first-hour action is applied.
- Thermal states are not in the LP; the plant model still enforces them.
- Hydrogen yield is linearised at believed specific energy.
- If HiGHS reports infeasible, a reserve-aware fallback dispatch is used.

### Why this is still MPC

It is genuine receding-horizon control: a multi-hour plan is solved, the first action is executed, the plant moves, the problem is solved again with a new forecast and a new estimate. It is not a single open-loop schedule.
