"""Receding-horizon MPC using a linear program (HiGHS via scipy).

At each step the controller:

1. Converts the weather *forecast* (not actual future) into PV availability.
2. Predicts SOC, H2 and CO2 storage over the horizon.
3. Maximises methane minus curtailment, cycling, reserve and startup proxies.
4. Applies only the first-hour setpoints.

Simplifications (documented in CONTROL_METHODOLOGY.md):

* Commitment binaries are relaxed; minimum load is enforced in the applied action.
* Thermal states are not in the LP; they are handled by plant physics and mode logic.
* Hydrogen yield is linearised at rated specific energy, derated by believed health.
* Charge and discharge may both be non-zero in the relaxation; the objective
  penalises throughput so simultaneous cycling is suboptimal.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from plantos.config import ExperimentConfig, PlantMode
from plantos.constants import CO2_PER_CH4_KG, H2_PER_CH4_KG
from plantos.controllers.base import Controller
from plantos.estimation.kalman import EstimatedState
from plantos.faults.reconfiguration import Reconfiguration
from plantos.plant.actions import ControlAction
from plantos.plant.solar import available_solar_mw
from plantos.weather.forecast import Forecast


class MPCController(Controller):
    name = "mpc"

    def __init__(self, config: ExperimentConfig):
        super().__init__(config)
        self._last_el = 0.0
        self._last_run = False

    def compute(
        self,
        belief: EstimatedState,
        forecast: Forecast,
        reconfig: Reconfiguration,
        dt_hours: float,
    ) -> ControlAction:
        plant = self.config.plant
        obj = self.config.mpc
        h = min(int(obj.horizon_hours), int(len(forecast.irradiance_wm2)), 48)
        h = max(h, 1)
        dt = dt_hours

        solar = np.array(
            [
                available_solar_mw(forecast.irradiance_wm2[i], forecast.temperature_c[i], plant.solar)
                for i in range(h)
            ]
        )
        # Current measured solar is more reliable for t=0 than the forecast.
        solar[0] = max(float(solar[0]), max(belief.solar_power_mw, 0.0))

        el_max = plant.electrolyser.max_power_mw * reconfig.capacity.get("electrolyser", 1.0)
        co2_max = plant.co2.max_power_mw * reconfig.capacity.get("co2_capture", 1.0)
        ch4_max = plant.methanation.max_ch4_kg_per_h * reconfig.capacity.get("methanation", 1.0)
        if "electrolyser" in reconfig.isolated:
            el_max = 0.0
        if "co2_capture" in reconfig.isolated:
            co2_max = 0.0
        if "methanation" in reconfig.isolated:
            ch4_max = 0.0
        # Emergency forbids battery discharge but still allows solar-following production.

        e_nom = plant.battery.energy_capacity_mwh * max(belief.battery_soh, 0.05)
        e_nom *= reconfig.capacity.get("battery", 1.0)
        eta_c = plant.battery.charge_efficiency
        eta_d = plant.battery.discharge_efficiency
        kwh_h2 = plant.electrolyser.nominal_kwh_per_kg / max(belief.electrolyser_health, 0.3)
        kwh_co2 = plant.co2.kwh_per_kg / max(plant.co2.capture_efficiency * belief.co2_capture_health, 0.2)
        aux = plant.auxiliary_mw
        k_meth = plant.methanation.aux_kwh_per_kg / 1000.0
        reserve = max(obj.soc_reserve, reconfig.soc_reserve)

        # Variable layout: [p_el | p_co2 | p_ch | p_dis | p_curt | ch4 | soc_slack] each length h
        # plus soc (h+1), h2 (h+1), co2 (h+1)
        n_grp = 7
        n = n_grp * h + 3 * (h + 1)
        pel, pco2, pch, pdis, pcurt, ch4, slack = (slice(i * h, (i + 1) * h) for i in range(7))
        soc = slice(n_grp * h, n_grp * h + (h + 1))
        h2s = slice(n_grp * h + (h + 1), n_grp * h + 2 * (h + 1))
        co2s = slice(n_grp * h + 2 * (h + 1), n_grp * h + 3 * (h + 1))

        c = np.zeros(n)
        c[ch4] = -obj.methane_weight
        c[pcurt] = obj.curtailment_penalty * 3.0  # strongly prefer using available solar
        c[pch] = obj.battery_stress_penalty + obj.degradation_penalty * 0.5
        c[pdis] = obj.battery_stress_penalty + obj.degradation_penalty * 0.5
        c[slack] = obj.reserve_penalty
        c[pel] += obj.startup_penalty * 0.02  # mild energy use penalty
        if reconfig.mode in {PlantMode.FORECAST_UNCERTAIN, PlantMode.POWER_CONSTRAINED, PlantMode.EMERGENCY}:
            c[pdis] += obj.risk_penalty * 0.25
            c[slack] += obj.risk_penalty * 0.2

        bounds = []
        for t in range(h):
            bounds.append((0.0, el_max))
        for t in range(h):
            bounds.append((0.0, co2_max))
        for t in range(h):
            bounds.append((0.0, plant.battery.max_charge_mw))
        for t in range(h):
            bounds.append((0.0, plant.battery.max_discharge_mw))
        for t in range(h):
            bounds.append((0.0, max(float(solar[t]), 0.0) + 1e-6))
        for t in range(h):
            bounds.append((0.0, ch4_max))
        for t in range(h):
            bounds.append((0.0, 1.0))
        for t in range(h + 1):
            bounds.append((plant.battery.soc_min, plant.battery.soc_max))
        for t in range(h + 1):
            bounds.append((0.0, plant.methanation.h2_storage_kg))
        for t in range(h + 1):
            bounds.append((0.0, plant.methanation.co2_storage_kg))

        a_eq = []
        b_eq = []
        a_ub = []
        b_ub = []

        def row() -> np.ndarray:
            return np.zeros(n)

        # Initial states
        r = row()
        r[soc.start] = 1.0
        a_eq.append(r)
        b_eq.append(float(np.clip(belief.battery_soc, plant.battery.soc_min, plant.battery.soc_max)))
        r = row()
        r[h2s.start] = 1.0
        a_eq.append(r)
        b_eq.append(float(np.clip(belief.h2_stored_kg, 0.0, plant.methanation.h2_storage_kg)))
        r = row()
        r[co2s.start] = 1.0
        a_eq.append(r)
        b_eq.append(float(np.clip(belief.co2_stored_kg, 0.0, plant.methanation.co2_storage_kg)))

        ramp = plant.electrolyser.ramp_mw_per_hour * dt
        ramp_c = plant.co2.ramp_mw_per_hour * dt

        for t in range(h):
            # Power balance
            r = row()
            r[pel.start + t] = 1.0
            r[pco2.start + t] = 1.0
            r[ch4.start + t] = k_meth
            r[pch.start + t] = 1.0
            r[pcurt.start + t] = 1.0
            r[pdis.start + t] = -1.0
            a_eq.append(r)
            b_eq.append(float(solar[t] - aux))

            # SOC dynamics
            r = row()
            r[soc.start + t + 1] = 1.0
            r[soc.start + t] = -1.0
            r[pch.start + t] = -(eta_c * dt) / max(e_nom, 1e-6)
            r[pdis.start + t] = (dt) / (eta_d * max(e_nom, 1e-6))
            a_eq.append(r)
            b_eq.append(0.0)

            # H2 dynamics
            r = row()
            r[h2s.start + t + 1] = 1.0
            r[h2s.start + t] = -1.0
            r[pel.start + t] = -(1000.0 / kwh_h2) * dt
            r[ch4.start + t] = H2_PER_CH4_KG * dt
            a_eq.append(r)
            b_eq.append(0.0)

            # CO2 dynamics
            r = row()
            r[co2s.start + t + 1] = 1.0
            r[co2s.start + t] = -1.0
            r[pco2.start + t] = -(1000.0 / kwh_co2) * dt
            r[ch4.start + t] = CO2_PER_CH4_KG * dt
            a_eq.append(r)
            b_eq.append(0.0)

            # Reserve: soc[t+1] + slack[t] >= reserve  =>  -soc - slack <= -reserve
            r = row()
            r[soc.start + t + 1] = -1.0
            r[slack.start + t] = -1.0
            a_ub.append(r)
            b_ub.append(-reserve)

            # Ramp electrolyser
            if t == 0:
                r = row()
                r[pel.start] = 1.0
                a_ub.append(r)
                b_ub.append(self._last_el + ramp)
                r = row()
                r[pel.start] = -1.0
                a_ub.append(r)
                b_ub.append(-self._last_el + ramp)
            else:
                r = row()
                r[pel.start + t] = 1.0
                r[pel.start + t - 1] = -1.0
                a_ub.append(r)
                b_ub.append(ramp)
                r = row()
                r[pel.start + t] = -1.0
                r[pel.start + t - 1] = 1.0
                a_ub.append(r)
                b_ub.append(ramp)

            if t > 0:
                r = row()
                r[pco2.start + t] = 1.0
                r[pco2.start + t - 1] = -1.0
                a_ub.append(r)
                b_ub.append(ramp_c)
                r = row()
                r[pco2.start + t] = -1.0
                r[pco2.start + t - 1] = 1.0
                a_ub.append(r)
                b_ub.append(ramp_c)

            # Methanation cannot exceed stored reactants (soft via dynamics + bounds).
            # Ramp methane
            if t > 0:
                max_d = plant.methanation.ramp_fraction_per_hour * ch4_max * dt
                r = row()
                r[ch4.start + t] = 1.0
                r[ch4.start + t - 1] = -1.0
                a_ub.append(r)
                b_ub.append(max_d)
                r = row()
                r[ch4.start + t] = -1.0
                r[ch4.start + t - 1] = 1.0
                a_ub.append(r)
                b_ub.append(max_d)

        A_eq = np.vstack(a_eq)
        A_ub = np.vstack(a_ub) if a_ub else None
        b_ub_v = np.array(b_ub) if b_ub else None

        result = linprog(
            c,
            A_ub=A_ub,
            b_ub=b_ub_v,
            A_eq=A_eq,
            b_eq=np.array(b_eq),
            bounds=bounds,
            method="highs",
            options={"time_limit": 0.25, "presolve": True},
        )

        if not result.success or result.x is None:
            return self._fallback(belief, reconfig, float(solar[0]))

        x = result.x
        el0 = float(max(x[pel.start], 0.0))
        co20 = float(max(x[pco2.start], 0.0))
        ch40 = float(max(x[ch4.start], 0.0))
        pch0 = float(max(x[pch.start], 0.0))
        pdis0 = float(max(x[pdis.start], 0.0))
        curt0 = float(max(x[pcurt.start], 0.0))
        batt = pdis0 - pch0
        meth_load = 0.0 if ch4_max < 1e-6 else float(np.clip(ch40 / max(ch4_max, 1e-6), 0.0, 1.0))
        if 0 < el0 < plant.electrolyser.min_stable_power_mw * 0.5:
            el0 = 0.0
        elif 0 < el0 < plant.electrolyser.min_stable_power_mw:
            el0 = min(plant.electrolyser.min_stable_power_mw, el_max)

        self._last_el = el0
        self._last_run = el0 > 0.2
        planned_ch4 = float(x[ch4].sum())
        text = (
            f"MPC {h}h horizon: stack {el0:.2f} MW, capture {co20:.2f} MW, "
            f"methane setpoint {ch40:.0f} kg/h, battery {batt:+.2f} MW, "
            f"curtail {curt0:.2f} MW. Reserve {reserve:.0%}. "
            f"Planned methane {planned_ch4:.0f} kg over horizon. Mode {reconfig.mode.value}."
        )
        return ControlAction(
            electrolyser_power_mw=el0,
            co2_capture_power_mw=co20,
            methanation_load=meth_load,
            battery_power_mw=batt,
            curtailment_mw=curt0,
            electrolyser_run=el0 >= plant.electrolyser.min_stable_power_mw * 0.45,
            isolate=set(reconfig.isolated),
            recover=set(reconfig.recover),
            explanation=text,
            reason_code="mpc.step",
            metadata={
                "horizon": h,
                "objective": float(result.fun) if result.fun is not None else None,
                "planned_methane_kg": planned_ch4,
                "reserve": reserve,
                "lp_success": True,
            },
        )

    def _fallback(self, belief: EstimatedState, reconfig: Reconfiguration, solar: float) -> ControlAction:
        plant = self.config.plant
        reserve = reconfig.soc_reserve
        el = 0.0
        if "electrolyser" not in reconfig.isolated and solar > 0.5 and belief.battery_soc > reserve:
            el = min(plant.electrolyser.max_power_mw * reconfig.capacity.get("electrolyser", 1.0), max(solar - 0.5, 0.0))
        return ControlAction(
            electrolyser_power_mw=el,
            co2_capture_power_mw=min(plant.co2.max_power_mw * 0.4, max(solar - el, 0.0)),
            methanation_load=0.5 if belief.h2_stored_kg > 40 else 0.0,
            electrolyser_run=el > 1.0,
            isolate=set(reconfig.isolated),
            recover=set(reconfig.recover),
            explanation="MPC LP infeasible; using reserve-aware fallback dispatch.",
            reason_code="mpc.fallback",
            metadata={"lp_success": False},
        )
