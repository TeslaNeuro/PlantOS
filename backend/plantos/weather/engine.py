# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Synthetic European weather and an external-data interface.

Clear-sky GHI uses a sine-elevation approximation (not a full REST2/Ineichen
model). Cloud cover is a regime-switching AR(1) process. Temperature is a
diurnal sinusoid plus a weather-dependent offset.

External files, if provided, must be CSV with columns:
    hour, irradiance_wm2, temperature_c, cloud_cover
No network APIs are imported by the core simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from plantos.config import WeatherConfig


@dataclass
class WeatherSample:
    hour: float
    irradiance_wm2: float
    temperature_c: float
    cloud_cover: float
    elevation_deg: float


def solar_elevation_deg(latitude_deg: float, day_of_year: int, hour_of_day: float) -> float:
    lat = np.radians(latitude_deg)
    decl = np.radians(23.45 * np.sin(np.radians(360.0 / 365.0 * (day_of_year - 81))))
    hour_angle = np.radians(15.0 * (hour_of_day - 12.0))
    sin_el = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    return float(np.degrees(np.arcsin(np.clip(sin_el, -1.0, 1.0))))


def clear_sky_ghi(elevation_deg: float) -> float:
    """Haurwitz-like clear-sky GHI (W/m²). Zero below the horizon."""
    if elevation_deg <= 0:
        return 0.0
    s = np.sin(np.radians(elevation_deg))
    return float(1093.0 * s * np.exp(-0.057 / max(s, 0.02)))


def ghi_from_cloud(clear_wm2: float, cloud_cover: float) -> float:
    """Kasten–Czeplak style cloud attenuation. cloud_cover in [0, 1]."""
    c = float(np.clip(cloud_cover, 0.0, 1.0))
    return float(max(clear_wm2 * (1.0 - 0.75 * c**3.4), 0.0))


def _regime_cloud_path(
    hours: int,
    dt_hours: float,
    rng: np.random.Generator,
    scenario: str,
) -> np.ndarray:
    """Mean cloud cover by scenario, with AR(1) residuals and rapid transitions."""
    t = np.arange(hours) * dt_hours
    day = t / 24.0
    if scenario == "clear":
        base = np.full(hours, 0.12)
    elif scenario == "cloudy":
        base = np.full(hours, 0.72)
    elif scenario == "rain":
        base = np.full(hours, 0.88)
    elif scenario == "storm":
        base = np.zeros(hours)
        for i, d in enumerate(day):
            if d < 2:
                base[i] = 0.18
            elif d < 3:
                base[i] = 0.10  # day 3 high solar
            elif d < 4:
                base[i] = 0.12  # day 4 morning still clear
            elif d < 4.5:
                # afternoon collapse
                base[i] = 0.12 + 0.75 * ((d - 4.0) / 0.5)
            elif d < 7:
                base[i] = 0.82
            elif d < 8:
                base[i] = 0.55
            elif d < 9:
                base[i] = 0.35
            else:
                base[i] = 0.15
    elif scenario == "cascade":
        base = 0.25 + 0.15 * np.sin(2 * np.pi * day / 3.0)
        base = np.clip(base, 0.1, 0.7)
    else:  # mixed 10-day European
        base = np.zeros(hours)
        pattern = [0.15, 0.20, 0.55, 0.25, 0.80, 0.70, 0.40, 0.22, 0.18, 0.12]
        for i, d in enumerate(day):
            di = min(int(d), len(pattern) - 1)
            frac = d - int(d)
            nxt = pattern[min(di + 1, len(pattern) - 1)]
            base[i] = (1 - frac) * pattern[di] + frac * nxt

    cloud = np.zeros(hours)
    eps = 0.0
    for i in range(hours):
        eps = 0.65 * eps + rng.normal(0.0, 0.08)
        # Occasional rapid cloud transition
        if rng.random() < 0.03:
            eps += rng.choice([-1.0, 1.0]) * rng.uniform(0.15, 0.35)
        cloud[i] = float(np.clip(base[i] + eps, 0.0, 1.0))
    return cloud


def generate_synthetic_weather(
    config: WeatherConfig,
    horizon_hours: int,
    dt_hours: float,
    seed: int,
) -> list[WeatherSample]:
    rng = np.random.default_rng(seed)
    n = int(round(horizon_hours / dt_hours))
    clouds = _regime_cloud_path(n, dt_hours, rng, config.scenario)
    samples: list[WeatherSample] = []
    for i in range(n):
        hour = i * dt_hours
        doy = config.start_day_of_year + int(hour // 24)
        hod = hour % 24.0
        el = solar_elevation_deg(config.latitude_deg, doy, hod)
        clear = clear_sky_ghi(el)
        ghi = ghi_from_cloud(clear, clouds[i])
        # Diurnal temperature, cooler when cloudy.
        t_mean = 18.0 - 6.0 * clouds[i]
        t = t_mean + 7.0 * np.sin(2 * np.pi * (hod - 10.0) / 24.0) + rng.normal(0, 0.4)
        samples.append(
            WeatherSample(
                hour=hour,
                irradiance_wm2=float(ghi),
                temperature_c=float(t),
                cloud_cover=float(clouds[i]),
                elevation_deg=el,
            )
        )
    return samples


def load_external_weather(path: str | Path) -> list[WeatherSample]:
    import csv

    samples: list[WeatherSample] = []
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hour = float(row["hour"])
            irr = float(row["irradiance_wm2"])
            temp = float(row["temperature_c"])
            cloud = float(row.get("cloud_cover", 0.0))
            samples.append(
                WeatherSample(
                    hour=hour,
                    irradiance_wm2=irr,
                    temperature_c=temp,
                    cloud_cover=cloud,
                    elevation_deg=0.0,
                )
            )
    if not samples:
        raise ValueError(f"No weather rows in {path}")
    return samples


def build_weather(config: WeatherConfig, horizon_hours: int, dt_hours: float, seed: int) -> list[WeatherSample]:
    if config.source == "external":
        if not config.external_path:
            raise ValueError("weather.source=external requires external_path")
        return load_external_weather(config.external_path)
    return generate_synthetic_weather(config, horizon_hours, dt_hours, seed)
