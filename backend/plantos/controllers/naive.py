"""Naive baseline: if solar is present, run everything; ignore forecast, faults and degradation."""

from __future__ import annotations

from plantos.controllers.base import Controller
from plantos.estimation.kalman import EstimatedState
from plantos.faults.reconfiguration import Reconfiguration
from plantos.plant.actions import ControlAction
from plantos.weather.forecast import Forecast


class NaiveController(Controller):
    name = "naive"

    def compute(
        self,
        belief: EstimatedState,
        forecast: Forecast,
        reconfig: Reconfiguration,
        dt_hours: float,
    ) -> ControlAction:
        solar = max(belief.solar_power_mw, 0.0)
        if solar < 0.25:
            return ControlAction(
                explanation="Night/low solar: naive controller idles all process units.",
                reason_code="naive.idle",
            )
        plant = self.config.plant
        remaining = max(solar - plant.auxiliary_mw, 0.0)
        # "Run everything" splits available power across process units by rating.
        el_max = plant.electrolyser.max_power_mw
        co2_max = plant.co2.max_power_mw
        share = el_max + co2_max
        el = remaining * el_max / share if share else 0.0
        co2 = remaining * co2_max / share if share else 0.0
        meth = 1.0
        return ControlAction(
            electrolyser_power_mw=el,
            co2_capture_power_mw=co2,
            methanation_load=meth,
            battery_power_mw=0.0,
            electrolyser_run=el >= plant.electrolyser.min_stable_power_mw * 0.5,
            explanation="Solar present: naive controller runs all available equipment without reserve or forecast.",
            reason_code="naive.run",
            metadata={"solar_mw": solar},
        )
