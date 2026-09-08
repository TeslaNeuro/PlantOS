# Experiments

## Reproducibility

Each experiment records seed, scenario YAML, controller and simulation settings. Replay with the same CLI command.

## Survival score

Configurable weights (defaults in `SurvivalScoreConfig`):

| Term | Default weight | Meaning |
|---|---|---|
| Production | 0.28 | Methane / (0.40 × nameplate × hours) |
| Availability | 0.16 | 1 − emergency/fault downtime fraction |
| Recovery speed | 0.14 | exp(−recovery_hours / 8) |
| Curtailment | 0.10 | 1 − curtailed/available solar |
| Battery reserve | 0.10 | Mean SOC above empty |
| Equipment health | 0.12 | Mean stack health and SOH |
| Fault tolerance | 0.10 | Production during active faults vs mean |

Weights are normalised. The score is a **competition index**, not a physical SI quantity.

Production is **not** scored against the same run’s own methane. That would give every controller a perfect production term, including a naive policy that barely produces.

## Storm test

`scenarios/storm.yaml`, seed 7, 240 h.

- Days 1–2 mixed
- Day 3 high solar
- Day 4 forecast failure (over-confident clear sky) while actual cloud collapses in the afternoon
- Day 5 electrolyser efficiency fault (hour 120, severity 0.35)
- Day 6 hydrogen sensor drift
- Days 7–10 recovery weather

Compare:

```bash
plantos compare --scenario storm --seed 7
```

Checked-in smoke results (re-run before quoting):

Storm test, seed 7, 240 h (from `plantos compare --scenario storm --seed 7`):

See `experiments/results/compare_storm.json`.

Monte Carlo smoke, n=8, seed 123: `experiments/results/monte_carlo_baseline_8.json`.

These are **not** a 100-run campaign. Run `plantos monte-carlo --runs 100` when you need a distribution. Quote numbers from a run you actually produced.

## Cascade test

Stacked battery capacity loss, electrolyser efficiency loss, methanation thermal stress, solar shading, and a biased noisy forecast.

Objective: keep the plant alive, not maximise a single sunny hour.

## Monte Carlo

```bash
plantos monte-carlo --runs 100 --scenario baseline --seed 123
```

Each draw randomises weather regime, forecast bias/noise/failure, fault type/timing/severity, sensor noise, initial SOC/SOH/health.

Output: mean / P10 / P50 / P90 per controller, JSON + CSV.

A 100-run, 10-day, 3-controller matrix is minutes to tens of minutes depending on MPC horizon. Start with `--runs 20` for a smoke test.

## Counterfactual

Identical disturbance, naive vs MPC:

```bash
plantos counterfactual --scenario storm
```

This is the “what would have happened without PlantOS” view. It is two simulations, not an analytical formula.

## 3-minute demonstration sequence

0:00 plant in NORMAL, schematic flowing  
0:20 forecast uncertainty / reserve language on the timeline  
0:40 day-4 forecast failure, GHI collapse vs forecast  
1:00 electrolyser efficiency residual  
1:20 diagnosis hypotheses  
1:40 derate / re-optimise, methane continues at reduced rate  
2:00 cascade or battery stress  
2:20 degraded production rather than black start  
2:40 comparison table: naive vs rules vs PlantOS (live numbers)
