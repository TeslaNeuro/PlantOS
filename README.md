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
  <a href="https://opensource.org/license/mit"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-4fc3f7?style=flat-square" /></a>
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3ddc97?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="https://fastapi.tiangolo.com/"><img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" /></a>
  <a href="https://react.dev/"><img alt="React console" src="https://img.shields.io/badge/console-React-61DAFB?style=flat-square&logo=react&logoColor=black" /></a>
  <img alt="Controllers" src="https://img.shields.io/badge/control-MPC%20%7C%20rules%20%7C%20naive-e8c547?style=flat-square" />
  <a href="https://docs.docker.com/compose/"><img alt="Docker" src="https://img.shields.io/badge/docker-compose-2496ED?style=flat-square&logo=docker&logoColor=white" /></a>
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
- 🎯 **Receding-horizon MPC** — linear program via [HiGHS](https://highs.dev/) ([SciPy](https://scipy.org/) `linprog`)
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

## 📦 Dependencies

Runtime packages link to their official sites:

<p>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="https://numpy.org/"><img alt="NumPy" src="https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white" /></a>
  <a href="https://scipy.org/"><img alt="SciPy" src="https://img.shields.io/badge/SciPy-8CAAE6?style=flat-square&logo=scipy&logoColor=white" /></a>
  <a href="https://docs.pydantic.dev/"><img alt="Pydantic" src="https://img.shields.io/badge/Pydantic-E92063?style=flat-square&logo=pydantic&logoColor=white" /></a>
  <a href="https://pyyaml.org/"><img alt="PyYAML" src="https://img.shields.io/badge/PyYAML-CB171E?style=flat-square" /></a>
  <a href="https://fastapi.tiangolo.com/"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" /></a>
  <a href="https://www.uvicorn.org/"><img alt="Uvicorn" src="https://img.shields.io/badge/Uvicorn-499848?style=flat-square" /></a>
  <a href="https://typer.tiangolo.com/"><img alt="Typer" src="https://img.shields.io/badge/Typer-2596BE?style=flat-square" /></a>
  <a href="https://github.com/Kludex/python-multipart"><img alt="python-multipart" src="https://img.shields.io/badge/python--multipart-2F2F2F?style=flat-square" /></a>
  <a href="https://highs.dev/"><img alt="HiGHS" src="https://img.shields.io/badge/HiGHS-solver-4fc3f7?style=flat-square" /></a>
</p>

Console:

<p>
  <a href="https://react.dev/"><img alt="React" src="https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black" /></a>
  <a href="https://vite.dev/"><img alt="Vite" src="https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white" /></a>
  <a href="https://www.typescriptlang.org/"><img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white" /></a>
</p>

Dev / deploy:

<p>
  <a href="https://docs.pytest.org/"><img alt="pytest" src="https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" /></a>
  <a href="https://docs.docker.com/"><img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" /></a>
</p>

Versions live in [`pyproject.toml`](pyproject.toml) and [`frontend/package.json`](frontend/package.json).

## 👤 Author

**TeslaNeuro** — [GitHub](https://github.com/TeslaNeuro)

## 📜 License

MIT. See [LICENSE](LICENSE).

Default plant ratings in `docs/ASSUMPTIONS.md` are a **reference model** for this repository, not manufacturer datasheets.
