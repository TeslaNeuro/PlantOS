"""Controller interface. Controllers see belief + forecast, never reality."""

from __future__ import annotations

from abc import ABC, abstractmethod

from plantos.config import ExperimentConfig
from plantos.estimation.kalman import EstimatedState
from plantos.faults.reconfiguration import Reconfiguration
from plantos.plant.actions import ControlAction
from plantos.weather.forecast import Forecast


class Controller(ABC):
    name: str = "base"

    def __init__(self, config: ExperimentConfig):
        self.config = config

    @abstractmethod
    def compute(
        self,
        belief: EstimatedState,
        forecast: Forecast,
        reconfig: Reconfiguration,
        dt_hours: float,
    ) -> ControlAction:
        raise NotImplementedError
