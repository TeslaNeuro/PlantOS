"""Competing-hypothesis fault diagnosis.

Do not label every residual as equipment failure. Compare four families:

* equipment degradation / actuator fault
* sensor fault (single-channel inconsistency)
* external disturbance (weather vs forecast)
* no-fault (noise)

Scores are heuristic likelihoods, not calibrated probabilities. They are
exposed to the operator as such.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.estimation.sensors import Measurement
from plantos.faults.detection import DetectionResult, ResidualSet


@dataclass
class Hypothesis:
    name: str
    probability: float
    explanation: str


@dataclass
class Diagnosis:
    hypotheses: list[Hypothesis]
    primary: str
    confidence: float
    component: str
    isolate: bool
    severity: float

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "confidence": self.confidence,
            "component": self.component,
            "isolate": self.isolate,
            "severity": self.severity,
            "hypotheses": [
                {"name": h.name, "probability": h.probability, "explanation": h.explanation}
                for h in self.hypotheses
            ],
        }


def diagnose(detection: DetectionResult, measurement: Measurement) -> Diagnosis:
    r: ResidualSet = detection.residuals
    scores = {
        "electrolyser_degradation": 0.05,
        "power_measurement_fault": 0.05,
        "hydrogen_sensor_fault": 0.05,
        "weather_disturbance": 0.05,
        "co2_capture_fault": 0.02,
        "battery_degradation": 0.02,
        "no_fault": 0.20,
    }

    if r.efficiency_pp < -6 and abs(r.electrolyser_power) < 0.4:
        scores["electrolyser_degradation"] += min(0.7, -r.efficiency_pp / 15.0)
    if abs(r.electrolyser_power) > 0.8 and abs(r.hydrogen) < 8:
        scores["power_measurement_fault"] += 0.45
    if abs(r.hydrogen) > 20 and abs(r.electrolyser_power) < 0.35 and r.efficiency_pp < -4:
        # Could be H2 sensor OR true efficiency. Prefer sensor if methane still tracks H2 poorly.
        scores["hydrogen_sensor_fault"] += 0.25
        scores["electrolyser_degradation"] += 0.35
    if r.solar_power < -1.0 and abs(r.efficiency_pp) < 4:
        scores["weather_disturbance"] += min(0.6, -r.solar_power / 4.0)
    if r.co2 < -40:
        scores["co2_capture_fault"] += 0.4
    if abs(r.soc) > 0.07:
        scores["battery_degradation"] += 0.35
    if detection.fault_type == "none" or detection.fault_probability < 0.3:
        scores["no_fault"] += 0.5

    # Frozen / failed measurement channels strongly favour sensor hypotheses.
    if "hydrogen_flow" in measurement.failed_channels or "hydrogen_flow" in measurement.frozen_channels:
        scores["hydrogen_sensor_fault"] += 0.7
        scores["electrolyser_degradation"] *= 0.4
    if "electrolyser_power" in measurement.failed_channels:
        scores["power_measurement_fault"] += 0.7

    total = sum(scores.values()) or 1.0
    probs = {k: v / total for k, v in scores.items()}
    ordered = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    explanations = {
        "electrolyser_degradation": "Hydrogen yield below digital-twin expectation at the measured stack power.",
        "power_measurement_fault": "Stack power disagrees with other electrical measurements; yield is consistent.",
        "hydrogen_sensor_fault": "Hydrogen flow is inconsistent while electrical load and methane remain coherent.",
        "weather_disturbance": "Measured solar is below the forecast-driven twin; plant internals look consistent.",
        "co2_capture_fault": "CO2 production residual exceeds persistence threshold.",
        "battery_degradation": "SOC innovation is larger than coulomb-count uncertainty.",
        "no_fault": "Residuals are within noise and persistence limits.",
    }
    hyps = [
        Hypothesis(name=k, probability=float(p), explanation=explanations[k])
        for k, p in ordered
    ]
    primary = ordered[0][0]
    conf = float(ordered[0][1])
    component = {
        "electrolyser_degradation": "electrolyser",
        "power_measurement_fault": "sensor",
        "hydrogen_sensor_fault": "sensor",
        "weather_disturbance": "solar",
        "co2_capture_fault": "co2_capture",
        "battery_degradation": "battery",
        "no_fault": "none",
    }[primary]
    isolate = False
    if primary == "electrolyser_degradation" and detection.fault_type == "electrolyser_complete" and detection.alarmed:
        isolate = True
    if primary == "co2_capture_fault" and conf >= 0.6 and detection.alarmed:
        isolate = True
    # Complete loss: isolate even if labelled degradation.
    if detection.fault_type == "electrolyser_complete" and detection.alarmed:
        isolate = True
        component = "electrolyser"
        primary = "electrolyser_degradation"
    severity = detection.fault_severity
    if primary == "electrolyser_degradation":
        severity = max(severity, float(np.clip(-r.efficiency_pp / 40.0, 0.0, 0.9)))
    return Diagnosis(
        hypotheses=hyps,
        primary=primary,
        confidence=conf,
        component=component,
        isolate=isolate,
        severity=severity,
    )
