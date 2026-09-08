<p align="center">
  <img src="docs/assets/banner.png" alt="PlantOS — autonomous plant operations" width="920" />
</p>

<p align="center">
  <img src="docs/assets/logo.png" alt="PlantOS logo" width="72" />
</p>

<h1 align="center">PlantOS</h1>

<p align="center">
  <strong>Self-healing operations for a solar-powered synthetic-fuel plant.</strong><br />
  Digital twin · receding-horizon MPC · fault diagnosis · live operations console
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-4fc3f7.png" alt="MIT license" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-3ddc97.png" alt="Python 3.11+" /></a>
  <img src="https://img.shields.io/badge/control-MPC%20%7C%20rules%20%7C%20naive-e8c547.png" alt="Controllers" />
</p>

---

PlantOS keeps a remote power-to-methane site **productive when the world disagrees with the plan**: intermittent solar, wrong forecasts, degrading equipment, and sensor faults.

It does not only chase a production setpoint. It **reconfigures** — isolate, derate, hold reserve, recover — so the plant still makes methane instead of waiting for a perfect day.

```
☀️ Weather  →  📡 Noisy forecast
🏭 Plant    →  🧪 Sensors  →  🧠 Estimator  →  🩺 FDD  →  🎯 Controller  →  ⚙️ Actuators
```

## ✨ Highlights

- ⚡ **Physics digital twin** — PV, battery, electrolyser, CO₂ capture, methanation, thermal states
- 🎯 **Receding-horizon MPC** — linear program via HiGHS (`scipy.optimize.linprog`)
- 🌦️ **Imperfect forecasts** — bias, AR(1) noise, and forecast dropouts
- 🩺 **Model-based FDD** — residuals, persistence, competing hypotheses
- 🛡️ **Autonomous recovery** — isolation, derating, graceful operating modes
- 🗣️ **Explainable actions** — machine-readable reason codes plus operator text
- 🖥️ **Operations console** — live compare of naive / rules / PlantOS MPC
- 📊 **Reproducible campaigns** — CLI experiments, Monte Carlo, counterfactuals

## 🧠 Reality vs belief

The platform keeps two worlds on purpose:

| World | What it contains |
|---|---|
| **Reality** | True physics, true weather, injected disturbances |
| **Belief** | Noisy sensors, a Kalman-style estimator, an imperfect forecast |

The controller **never** receives the actual future weather. If it looks clever, it earned it.

<p align="center">
  <img src="docs/assets/architecture.png" alt="PlantOS closed-loop architecture" width="820" />
</p>

## 🚀 Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]" --config-settings editable_mode=compat
pytest -q
plantos simulate --scenario storm --controller mpc
plantos compare --scenario storm
```

### 🖥️ Operations console

```bash
# terminal 1 — API
plantos serve --port 8000

# terminal 2 — console
cd frontend && npm install && npm run dev
```

Open [http://localhost:5173](http://localhost:5173). **Run compare** executes live naive / rules / MPC simulations — not a canned animation.

### 🐳 Docker

```bash
docker compose up --build
```

API on **8000**, console on **5173**.

## 🎮 Controllers

| Name | Emoji | Role |
|---|---|---|
| `naive` | 🌞 | Run process load when solar is present. No forecast, isolation, or recovery. |
| `rules` | 📋 | Reserve, minimum run time, poor-weather starts, scarcity shedding. |
| `mpc` | 🎯 | 24–48 h receding-horizon LP. This is PlantOS. |

## 🧪 CLI

```bash
plantos simulate --scenario storm --controller mpc
plantos compare --scenario storm
plantos monte-carlo --runs 20 --scenario baseline
plantos fault-test --type electrolyser_efficiency
plantos counterfactual --scenario storm
plantos serve --port 8000
```

Scenarios live in [`scenarios/`](scenarios/): **storm**, **cascade**, **baseline**.

Results write to `experiments/results/`. Numbers in the console and CLI come from the simulator for that run.

## 📚 Documentation

| Doc | What’s inside |
|---|---|
| [Technical architecture](docs/TECHNICAL_ARCHITECTURE.md) | Twin, estimator, API, invariants |
| [Control methodology](docs/CONTROL_METHODOLOGY.md) | Naive, rules, MPC formulation |
| [Fault methodology](docs/FAULT_METHODOLOGY.md) | Injection, detection, diagnosis, recovery |
| [Plant model](docs/ASSUMPTIONS.md) | Default parameters and modelling scope |
| [Experiments](docs/EXPERIMENTS.md) | Survival score, storm / cascade / Monte Carlo |
| [Operations console](docs/CONSOLE.md) | Dashboard walkthrough |

## 🏗️ Repository layout

```
backend/plantos/     Python package (physics, control, FDD, API, CLI)
frontend/            React operations console
scenarios/           YAML plant + weather + fault campaigns
docs/                Architecture and methodology
docker/              Backend and console images
experiments/results/ CLI output (generated)
```

## 🔧 Tests

```bash
pytest -q
```

Every simulation step checks power balance, mass balance, SOC limits, ramp limits, and isolated equipment.

## 👤 Author

**TeslaNeuro** — [GitHub](https://github.com/TeslaNeuro)

## 📜 License

MIT. See [LICENSE](LICENSE).

Default plant ratings in `docs/ASSUMPTIONS.md` are a **reference model** for this repository, not manufacturer datasheets.
