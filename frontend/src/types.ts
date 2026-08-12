export type Reality = {
  hour: number;
  solar_power_mw: number;
  solar_available_mw: number;
  curtailed_power_mw: number;
  battery_soc: number;
  battery_soh: number;
  battery_power_mw: number;
  electrolyser_power_mw: number;
  electrolyser_health: number;
  electrolyser_temperature_c: number;
  electrolyser_status: string;
  hydrogen_rate_kgph: number;
  co2_capture_power_mw: number;
  co2_capture_health: number;
  co2_rate_kgph: number;
  methanation_load: number;
  methanation_power_mw: number;
  methanation_health: number;
  methanation_temperature_c: number;
  methane_rate_kgph: number;
  h2_stored_kg: number;
  co2_stored_kg: number;
  methane_total_kg: number;
  plant_load_mw: number;
  plant_mode: string;
  irradiance_wm2: number;
  ambient_temp_c: number;
  cloud_cover: number;
  isolated_components: string[];
  active_faults: { fault_type: string; component: string; severity: number; active: boolean }[];
};

export type EventRow = {
  hour: number;
  reason_code: string;
  explanation: string;
  mode: string;
  diagnosis?: {
    primary: string;
    confidence: number;
    hypotheses?: { name: string; probability: number; explanation: string }[];
  };
};

export type Metrics = {
  methane_total_kg: number;
  curtailment_fraction: number;
  downtime_hours: number;
  survival_score: number;
  availability: number;
  min_soc: number;
  recovery_hours: number | null;
  fault_production_ratio: number;
  soh_loss: number;
  mean_methane_kgph: number;
};

export type ComparePayload = {
  id?: string;
  scenario: string;
  seed: number;
  controllers: Record<string, Metrics>;
  timeseries: Record<string, Reality[]>;
  weather: { hour: number; irradiance_wm2: number; temperature_c: number; cloud_cover: number }[];
  full_events: Record<string, EventRow[]>;
  counterfactual: {
    without: Metrics;
    with: Metrics;
    methane_saved_kg: number;
    downtime_avoided_hours: number;
  };
};

export type RunPayload = {
  id?: string;
  controller: string;
  seed: number;
  metrics: Metrics;
  events: EventRow[];
  timeseries: Reality[];
  weather: { hour: number; irradiance_wm2: number; temperature_c: number }[];
};
