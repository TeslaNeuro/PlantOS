from plantos.config import ControllerType, ExperimentConfig
from plantos.controllers.base import Controller
from plantos.controllers.mpc import MPCController
from plantos.controllers.naive import NaiveController
from plantos.controllers.rules import RuleController


def make_controller(config: ExperimentConfig) -> Controller:
    if config.controller == ControllerType.NAIVE:
        return NaiveController(config)
    if config.controller == ControllerType.RULES:
        return RuleController(config)
    if config.controller == ControllerType.MPC:
        return MPCController(config)
    raise ValueError(f"Unknown controller {config.controller}")


__all__ = ["Controller", "MPCController", "NaiveController", "RuleController", "make_controller"]
