# PlantOS

Autonomous self-healing control for a remote synthetic-fuel plant powered by intermittent solar.

> **PlantOS does not simply optimise production. It continuously reconfigures the plant to remain productive when reality deviates from the expected operating plan.**

This is a research prototype, not an operational DCS. Every performance number in this repository is produced by the simulator. None are hard-coded.

## Research question

Can an industrial plant remain productive and recover autonomously when renewable power is intermittent, forecasts are wrong, equipment degrades, sensors fail and human intervention is unavailable?

## What is implemented

1. Physics-based digital twin (PV, battery, electrolyser, CO₂ capture, methanation, thermal states)
2. Renewable-aware scheduling
3. Receding-horizon MPC (linear program, HiGHS)
4. Forecast uncertainty (bias, AR(1) noise, forecast failure)
5. Model-based fault detection (residuals + persistence)
6. Competing-hypothesis diagnosis (equipment vs sensor vs weather)
7. Autonomous isolation / derating / recovery
8. Graceful degradation and operating modes
9. Equipment degradation (battery SOH, stack health, thermal stress)
10. Explainable decisions (machine-readable reason codes + operator text)
11. Monte Carlo robustness testing and controller comparison

## Reality vs belief

The simulator keeps two worlds:

- **Reality** — true plant physics, true weather, injected faults
- **Controller belief** — noisy sensors, a Kalman-style estimator, and an imperfect forecast

The controller never receives the actual future weather.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
plantos simulate --scenario storm --controller mpc
plantos compare --scenario storm
plantos counterfactual --scenario storm
```

Dashboard:

```bash
# terminal 1
plantos serve --port 8000
# terminal 2
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. **Run compare** executes live simulations (naive / rules / MPC). It is not a canned animation.

Docker:

```bash
docker compose up --build
```

API on port 8000, console on port 5173.

## CLI

```bash
plantos simulate --scenario storm --controller mpc
plantos compare --scenario storm
plantos monte-carlo --runs 20 --scenario baseline
plantos fault-test --type electrolyser_efficiency
plantos counterfactual --scenario storm
```

Scenarios live in `scenarios/`: `storm`, `cascade`, `baseline`.

## Architecture

```
Weather (actual) → Forecast engine (noisy)
Plant reality    → Sensors → Estimator → Digital twin residuals
                                      → FDD → Reconfiguration → Controller
                                      → Actuators → Plant reality
```

See `docs/TECHNICAL_ARCHITECTURE.md`.

## Controllers

| Name | Role |
|---|---|
| `naive` | If solar is present, run everything. No forecast, isolation or recovery. |
| `rules` | Reserve, min run time, poor-weather starts, scarcity shedding. |
| `mpc` | 24–48 h receding-horizon LP. PlantOS. |

## Experiments

Results are written to `experiments/results/`. Do not quote numbers that you have not just generated.

Storm test (10 days, seed 7) is the cinematic demo. Cascade injects stacked faults. Monte Carlo randomises weather, forecast error, faults, sensors and initial health.

## Tests

```bash
pytest -q
```

Invariant checks run inside every simulation step: power balance, mass balance, SOC limits, ramp-up limits, isolated equipment.

## Documentation

- `docs/TECHNICAL_ARCHITECTURE.md`
- `docs/CONTROL_METHODOLOGY.md`
- `docs/FAULT_METHODOLOGY.md`
- `docs/ASSUMPTIONS.md`
- `docs/EXPERIMENTS.md`

## Licence

Research prototype. Parameters marked “invented” in the assumptions document are not manufacturer data.
