# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""PlantOS command-line interface.

Author: TeslaNeuro
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from plantos.experiments.runner import (
    compare_controllers,
    counterfactual,
    fault_test,
    monte_carlo,
    simulate,
    write_csv_summary,
    write_json,
)

app = typer.Typer(help="PlantOS — simulate, compare, and operate the digital twin.", add_completion=False)
OUT = Path("experiments/results")


@app.command("simulate")
def simulate_cmd(
    scenario: str = typer.Option("storm", "--scenario", "-s"),
    controller: str = typer.Option("mpc", "--controller", "-c"),
    seed: Optional[int] = typer.Option(None, "--seed"),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Run a single closed-loop simulation."""
    res = simulate(scenario, controller, seed)
    m = res.metrics
    typer.echo(
        f"{res.controller}  methane={m.methane_total_kg:.1f} kg  "
        f"curtail={100*m.curtailment_fraction:.1f}%  "
        f"downtime={m.downtime_hours:.1f}h  "
        f"survival={m.survival_score:.3f}  minSOC={m.min_soc:.2f}"
    )
    dest = out or OUT / f"{scenario}_{controller}_{res.seed}.json"
    write_json(res.to_serializable(thin=True), dest)
    typer.echo(f"wrote {dest}")


@app.command("compare")
def compare_cmd(
    scenario: str = typer.Option("storm", "--scenario", "-s"),
    seed: Optional[int] = typer.Option(None, "--seed"),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Compare naive, rules and MPC on the same scenario."""
    cmp = compare_controllers(scenario, seed)
    typer.echo(f"{'controller':<10} {'methane_kg':>12} {'curtail':>10} {'downtime_h':>12} {'survival':>10}")
    for ctrl, m in cmp["controllers"].items():
        typer.echo(
            f"{ctrl:<10} {m['methane_total_kg']:12.1f} {100*m['curtailment_fraction']:9.1f}% "
            f"{m['downtime_hours']:12.1f} {m['survival_score']:10.3f}"
        )
    dest = out or OUT / f"compare_{scenario}.json"
    write_json(cmp, dest)
    typer.echo(f"wrote {dest}")


@app.command("monte-carlo")
def monte_cmd(
    runs: int = typer.Option(100, "--runs", "-n"),
    scenario: str = typer.Option("baseline", "--scenario", "-s"),
    seed: int = typer.Option(123, "--seed"),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Monte Carlo robustness test across randomised disturbances."""
    mc = monte_carlo(n_runs=runs, base_scenario=scenario, seed=seed)
    typer.echo(f"{'':16} {'Naive':>14} {'Rules':>14} {'PlantOS':>14}")
    for metric in ("methane_total_kg", "curtailment_fraction", "downtime_hours", "survival_score"):
        n = mc["summary"]["naive"][metric]["mean"]
        r = mc["summary"]["rules"][metric]["mean"]
        p = mc["summary"]["mpc"][metric]["mean"]
        typer.echo(f"{metric:<16} {n:14.3f} {r:14.3f} {p:14.3f}")
    dest = out or OUT / f"monte_carlo_{scenario}_{runs}.json"
    write_json(mc, dest)
    csv_path = dest.with_suffix(".csv")
    write_csv_summary(mc, csv_path)
    typer.echo(f"wrote {dest} and {csv_path}")


@app.command("fault-test")
def fault_cmd(
    type: str = typer.Option("electrolyser_efficiency", "--type", "-t"),
    controller: str = typer.Option("mpc", "--controller", "-c"),
    seed: int = typer.Option(5, "--seed"),
) -> None:
    """Inject a single fault type on the baseline plant."""
    res = fault_test(type, controller, seed)
    typer.echo(
        f"fault={type} controller={controller} methane={res.metrics.methane_total_kg:.1f} "
        f"survival={res.metrics.survival_score:.3f} downtime={res.metrics.downtime_hours:.1f}h"
    )
    dest = OUT / f"fault_{type}_{controller}.json"
    write_json(res.to_serializable(thin=True), dest)
    typer.echo(f"wrote {dest}")


@app.command("counterfactual")
def counterfactual_cmd(
    scenario: str = typer.Option("storm", "--scenario", "-s"),
    seed: Optional[int] = typer.Option(None, "--seed"),
) -> None:
    """What would have happened without PlantOS (naive vs MPC)."""
    cf = counterfactual(scenario, seed)
    typer.echo("WITHOUT PlantOS")
    for line in cf["without_plantos"]["narrative"]:
        typer.echo(f"  {line}")
    typer.echo("WITH PlantOS")
    for line in cf["with_plantos"]["narrative"]:
        typer.echo(f"  {line}")
    typer.echo(f"Methane saved: {cf['methane_saved_kg']:.1f} kg")
    dest = OUT / f"counterfactual_{scenario}.json"
    write_json(cf, dest)
    typer.echo(f"wrote {dest}")


@app.command("serve")
def serve(
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """Start the FastAPI control-room backend."""
    import uvicorn

    uvicorn.run("plantos.api.app:app", host=host, port=port, reload=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
