# Technical architecture

The simulator is the plant. The API and console only *drive* and *display* it.

## Split between reality and belief

`plantos.simulation.engine.Simulator` is the only place the two worlds meet.

1. The fault engine applies scenario disturbances to **reality** and to the sensor bank.
2. The forecast engine issues a noisy forecast from the actual future (the controller never sees that future).
3. Sensors measure reality.
4. The estimator updates **belief**.
5. Fault detection compares belief + forecast-driven twin expectations to measurements.
6. Diagnosis ranks competing hypotheses.
7. Reconfiguration updates mode, isolation and capacity **for PlantOS and rules only**. The naive controller does not isolate or recover.
8. The controller computes an action from belief + forecast + reconfiguration.
9. `step_plant` advances reality, clipping actions to physics.

```
Weather (actual) → Forecast engine (noisy)
Plant reality    → Sensors → Estimator → Digital twin residuals
                                      → FDD → Reconfiguration → Controller
                                      → Actuators → Plant reality
```

## Plant physics (`plantos.plant`)

| Module | Role |
|---|---|
| `solar.py` | STC derate, NOCT cell temperature, inverter clip, curtailment |
| `battery.py` | SOC/SOH, efficiency, throughput degradation |
| `electrolyser.py` | State machine, part-load specific energy, ramp, thermal |
| `co2.py` | Electrical DAC-style capture |
| `methanation.py` | Sabatier mass balance, thermal lag, storage tanks |
| `plant.py` | Islanded power allocation, protection trips |
| `invariants.py` | Hard checks each step |

Islanded bus:

```
P_solar_used + P_discharge = P_el + P_co2 + P_meth_aux + P_aux + P_charge
P_solar_used + P_curtail   = P_solar_available
```

If a controller over-commits from a wrong SOC estimate, protection sheds process load. Energy is never created.

## Weather and forecast

`weather.engine` generates synthetic mid-latitude GHI and temperature. `weather.forecast.ForecastEngine` adds AR(1) error, bias, and optional failure (over-confident clear sky).

## Estimation

`SensorBank` corrupts selected channels. `StateEstimator` runs independent scalar Kalman filters. Tank levels are integrated from estimated flows, not read from reality. Health/SOH in belief are updated from diagnosis, not from hidden true health.

Electrolyser **status** is treated as PLC feedback (the command path). That is not a leak of the future.

## Faults

YAML-configurable injection (`FaultSpec`). Detection uses digital-twin residuals with persistence. Diagnosis compares equipment, sensor, and weather hypotheses. Reconfiguration derates or isolates and later recovers after quiet residuals.

## Controllers

See [CONTROL_METHODOLOGY.md](CONTROL_METHODOLOGY.md).

## API

FastAPI in `plantos.api.app`. Simulation logic does not import UI code. The frontend is a consumer of HTTP.

## Reproducibility

Every run binds: random seed, scenario YAML, controller, simulation `dt`, and horizon. Identical seeds replay identical weather, forecast noise, and sensor noise.
