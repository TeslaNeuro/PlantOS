# Fault methodology

## Injection

Scenario YAML, for example:

```yaml
faults:
  faults:
    - type: electrolyser_efficiency
      start_hour: 120
      severity: 0.35
    - type: sensor_drift
      start_hour: 144
      component: hydrogen_flow
      severity: 1.2
```

Supported families: solar shading, battery capacity/losses/thermal, electrolyser efficiency/partial/complete, CO₂ reduced/complete, methanation throughput/thermal, sensor bias/drift/freeze/fail.

The controller does not read this list. It must infer faults from residuals.

## Detection

One-step digital-twin expectations (hydrogen from measured/estimated stack power and believed health; PV from the **forecast**, not from actual GHI) are subtracted from measurements.

Alarms require persistence (default 2 h) so Gaussian sensor noise does not trip the plant.

Startup, shutdown and off states do **not** generate efficiency alarms: purge yield is not a stack fault.

## Diagnosis

Heuristic competing hypotheses, renormalised to 1:

- electrolyser degradation
- power measurement fault
- hydrogen sensor fault
- weather disturbance
- CO₂ capture fault
- battery degradation
- no fault

Isolation is reserved for complete equipment loss. Efficiency loss is **derated**, not tripped, so partial production continues.

## Reconfiguration

Modes: `NORMAL`, `FORECAST_UNCERTAIN`, `POWER_CONSTRAINED`, `DEGRADED`, `FAULT`, `EMERGENCY`, `RECOVERY`.

Naive does not use this layer. Rules and MPC do.

Recovery: if equipment residuals stay quiet for 4 h, isolated units are offered back to the controller.

## What we do not claim

Hypothesis percentages are not calibrated posteriors. Detection thresholds are not SIL-rated. The value of the method is that it **distinguishes sensor, weather and equipment** instead of labelling every residual as a trip.
