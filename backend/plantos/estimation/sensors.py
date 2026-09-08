# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Noisy, biased, drifting and failing sensors.

The controller never reads PlantState fields from reality. It only sees
``Measurement`` objects produced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from plantos.config import SensorChannelConfig, SensorConfig
from plantos.plant.state import PlantState


@dataclass
class Measurement:
    hour: float
    values: dict[str, float]
    failed_channels: set[str] = field(default_factory=set)
    frozen_channels: set[str] = field(default_factory=set)

    def get(self, name: str, default: float = 0.0) -> float:
        return float(self.values.get(name, default))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "values": dict(self.values),
            "failed_channels": sorted(self.failed_channels),
            "frozen_channels": sorted(self.frozen_channels),
        }


CHANNEL_MAP = {
    "solar_power": lambda s: s.solar_power_mw,
    "battery_soc": lambda s: s.battery_soc,
    "battery_power": lambda s: s.battery_power_mw,
    "electrolyser_power": lambda s: s.electrolyser_power_mw,
    "hydrogen_flow": lambda s: s.hydrogen_rate_kgph,
    "co2_flow": lambda s: s.co2_rate_kgph,
    "methane_flow": lambda s: s.methane_rate_kgph,
    "electrolyser_temperature": lambda s: s.electrolyser_temperature_c,
    "methanation_temperature": lambda s: s.methanation_temperature_c,
    "co2_power": lambda s: s.co2_capture_power_mw,
}


class SensorBank:
    def __init__(self, config: SensorConfig, seed: int):
        self.config = config
        self.rng = np.random.default_rng(seed + 91)
        self.drift: dict[str, float] = {k: 0.0 for k in CHANNEL_MAP}
        self.last_good: dict[str, float] = {k: 0.0 for k in CHANNEL_MAP}
        self.forced_fail: dict[str, str] = {}  # channel -> 'fail'|'freeze'|'bias'|'drift'
        self.forced_bias: dict[str, float] = {}
        self.forced_drift: dict[str, float] = {}

    def inject(self, channel: str, mode: str, magnitude: float = 0.0) -> None:
        self.forced_fail[channel] = mode
        if mode == "bias":
            self.forced_bias[channel] = magnitude
        if mode == "drift":
            self.forced_drift[channel] = magnitude

    def clear(self, channel: str | None = None) -> None:
        if channel is None:
            self.forced_fail.clear()
            self.forced_bias.clear()
            self.forced_drift.clear()
        else:
            self.forced_fail.pop(channel, None)
            self.forced_bias.pop(channel, None)
            self.forced_drift.pop(channel, None)

    def measure(self, state: PlantState, dt_hours: float) -> Measurement:
        values: dict[str, float] = {}
        failed: set[str] = set()
        frozen: set[str] = set()
        for name, getter in CHANNEL_MAP.items():
            ch: SensorChannelConfig = getattr(self.config, name)
            truth = float(getter(state))
            mode = self.forced_fail.get(name)
            self.drift[name] += (ch.drift_per_hour + self.forced_drift.get(name, 0.0)) * dt_hours
            if mode == "fail" or (mode is None and ch.fail_probability > 0 and self.rng.random() < ch.fail_probability):
                values[name] = 0.0
                failed.add(name)
                continue
            if mode == "freeze":
                values[name] = self.last_good[name]
                frozen.add(name)
                continue
            noise = self.rng.normal(0.0, ch.noise_std)
            bias = ch.bias + self.forced_bias.get(name, 0.0) + self.drift[name]
            y = truth + bias + noise
            if name == "battery_soc":
                y = float(np.clip(y, 0.0, 1.0))
            values[name] = float(y)
            self.last_good[name] = values[name]
        return Measurement(hour=state.hour, values=values, failed_channels=failed, frozen_channels=frozen)
