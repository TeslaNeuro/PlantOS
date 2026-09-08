# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Monte Carlo seed reproducibility (tiny draw, not the 100-run campaign)."""

from __future__ import annotations

import numpy as np

from plantos.config import ExperimentConfig
from plantos.experiments.runner import _randomize_config


def test_randomize_config_deterministic():
    base = ExperimentConfig(name="mc")
    a = _randomize_config(base, np.random.default_rng(99))
    b = _randomize_config(base, np.random.default_rng(99))
    c = _randomize_config(base, np.random.default_rng(100))
    assert a.simulation.seed == b.simulation.seed
    assert a.forecast.bias_wm2 == b.forecast.bias_wm2
    assert a.simulation.seed != c.simulation.seed
