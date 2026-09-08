# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Rule-based controller: reserve, min run time, forecast-aware starts, scarcity shedding."""

from __future__ import annotations

from plantos.controllers.base import Controller
from plantos.estimation.kalman import EstimatedState
from plantos.faults.reconfiguration import Reconfiguration
from plantos.plant.actions import ControlAction
from plantos.weather.forecast import Forecast
from plantos.plant.solar import available_solar_mw


class RuleController(Controller):
    name = "rules"

    def __init__(self, config):
        super().__init__(config)
        self._run_hours = 0.0
        self._was_running = False

    def compute(
        self,
        belief: EstimatedState,
        forecast: Forecast,
        reconfig: Reconfiguration,
        dt_hours: float,
    ) -> ControlAction:
        cfg = self.config.rules
        plant = self.config.plant
        reserve = max(cfg.soc_reserve, reconfig.soc_reserve)
        solar = max(belief.solar_power_mw, 0.0)

        look = min(cfg.look_ahead_hours, len(forecast.irradiance_wm2))
        future = []
        for i in range(look):
            irr, temp, _ = forecast.at(i)
            future.append(available_solar_mw(irr, temp, plant.solar))
        mean_future = sum(future) / max(len(future), 1)
        poor = mean_future < cfg.poor_weather_wm2 / 1000.0 * plant.solar.capacity_mw * 0.35

        isolated = reconfig.isolated | belief.isolated_components
        el_cap = reconfig.capacity.get("electrolyser", 1.0)
        co2_cap = reconfig.capacity.get("co2_capture", 1.0)

        scarcity = belief.battery_soc < cfg.scarcity_soc
        defend = belief.battery_soc < reserve + 0.03

        run_el = "electrolyser" not in isolated and el_cap > 0.1
        if solar < 0.2 and belief.battery_soc < reserve + 0.08:
            run_el = False
        if poor and not self._was_running and belief.battery_soc < 0.6:
            run_el = False
        if self._was_running and self._run_hours < cfg.min_run_hours and belief.battery_soc > reserve:
            run_el = "electrolyser" not in isolated

        budget = solar
        if belief.battery_soc > reserve + 0.05 and not defend:
            budget += min(plant.battery.max_discharge_mw * 0.4, 2.0)
        budget = max(budget - plant.auxiliary_mw, 0.0)

        el = 0.0
        co2 = 0.0
        meth = 0.0
        reason = "rules.idle"
        text = "Holding process units off to defend battery reserve."

        if run_el:
            target = plant.electrolyser.max_power_mw * el_cap
            if defend or scarcity:
                target *= 0.45 if scarcity else 0.65
            if poor:
                target *= 0.7
            el = min(target, budget)
            if 0 < el < plant.electrolyser.min_stable_power_mw:
                el = 0.0 if el < 0.5 * plant.electrolyser.min_stable_power_mw else min(
                    plant.electrolyser.min_stable_power_mw, budget
                )
            budget -= el
            reason = "rules.produce"
            text = (
                f"Rule stack {el:.1f} MW, reserve target {reserve:.0%}, "
                f"6h mean forecast PV {mean_future:.1f} MW."
            )

        if "co2_capture" not in isolated and budget > plant.co2.min_power_mw:
            co2 = min(plant.co2.max_power_mw * co2_cap, budget * 0.85)
            if scarcity:
                co2 *= 0.5
            budget -= co2

        h2_ok = belief.h2_stored_kg > 30 or el > 1.0
        if h2_ok and belief.co2_stored_kg > 50:
            meth = 0.85 if not scarcity else 0.45
            if reconfig.mode.value in {"POWER_CONSTRAINED", "EMERGENCY"}:
                meth = min(meth, 0.4)
        if "methanation" in isolated:
            meth = 0.0

        if el > 0:
            self._run_hours += dt_hours
            self._was_running = True
        else:
            if self._was_running:
                self._run_hours = 0.0
            self._was_running = False

        if reconfig.mode.value == "EMERGENCY":
            el, co2, meth = 0.0, 0.0, 0.0
            reason = "rules.emergency"
            text = "Emergency shed: process load to zero, battery reserve only."

        return ControlAction(
            electrolyser_power_mw=max(el, 0.0),
            co2_capture_power_mw=max(co2, 0.0),
            methanation_load=max(min(meth, 1.0), 0.0),
            battery_power_mw=0.0,
            electrolyser_run=el >= plant.electrolyser.min_stable_power_mw * 0.45,
            isolate=set(reconfig.isolated),
            recover=set(reconfig.recover),
            explanation=text,
            reason_code=reason,
            metadata={"reserve": reserve, "mean_future_pv_mw": mean_future, "poor_weather": poor},
        )
