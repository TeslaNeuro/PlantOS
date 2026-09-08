# Operations console

The PlantOS console is a live **operations center** for closed-loop simulations. It is not a slide deck: **Run compare** executes naive, rules, and MPC on the selected scenario.

## Start

```bash
plantos serve --port 8000
cd frontend && npm install && npm run dev
```

Open http://localhost:5173.

## Suggested walkthrough (storm, seed 7)

1. Leave **Scenario** on Storm test and **Controller** on PlantOS MPC, then **Run compare**.
2. Press **Play**. Solar, hydrogen, and methane flows animate on the schematic; the white line on the chart is the current hour.
3. Scrub to **hour 120** (D6 00:00). The electrolyser efficiency disturbance should show as a fault, with MPC fallback language in the timeline.
4. Switch **Controller** to Rules or Naive on the same run to compare decisions without re-simulating.

| Control | What it does |
|---|---|
| Scenario | Storm, cascade, or baseline. Changing it re-runs compare. |
| Controller | Playback of that controller's timeseries and events. |
| Play / ±1 h / slider | Move through the 240-hour horizon. |

## Reading the screen

- **Status pill** is operating *mode* (policy), not a health bar.
- **Health** bars are component condition. Mode can be `DEGRADED` while bars are still high.
- **Survival** is a run-level index for the selected controller, not a live hourly KPI.

See also [Experiments](EXPERIMENTS.md) for what the storm campaign injects.
