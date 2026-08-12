import { useEffect, useMemo, useState } from "react";
import { compareSimulation } from "./api";
import type { ComparePayload, EventRow, Reality } from "./types";

const modeClass = (mode: string) => {
  if (["FAULT", "EMERGENCY"].includes(mode)) return "fault";
  if (["DEGRADED", "POWER_CONSTRAINED", "FORECAST_UNCERTAIN"].includes(mode)) return "warn";
  return "good";
};

const fmtHour = (h: number) => {
  const d = Math.floor(h / 24) + 1;
  const hh = Math.floor(h % 24);
  return `D${d} ${String(hh).padStart(2, "0")}:00`;
};

function Spark({
  series,
  color,
  max,
}: {
  series: number[];
  color: string;
  max?: number;
}) {
  const w = 520;
  const h = 140;
  const m = max ?? Math.max(...series, 1e-6);
  const pts = series
    .map((v, i) => {
      const x = (i / Math.max(series.length - 1, 1)) * w;
      const y = h - (v / m) * (h - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polyline fill="none" stroke={color} strokeWidth="1.6" points={pts} />
    </svg>
  );
}

function PlantSchematic({ s }: { s: Reality }) {
  const iso = new Set(s.isolated_components || []);
  const failed = (name: string) => iso.has(name) || (s.active_faults || []).some((f) => f.component === name && f.active);
  const on = (p: number) => (p > 0.15 ? "flow" : "flow off");
  return (
    <svg className="plant" viewBox="0 0 760 420">
      <text className="node-label" x="40" y="28">
        POWER / MATERIAL PATH
      </text>
      <rect className={`node-box ${failed("solar") ? "failed" : ""}`} x="40" y="50" width="140" height="64" />
      <text className="node-label" x="52" y="72">
        SOLAR PV
      </text>
      <text className="node-val" x="52" y="96">
        {s.solar_power_mw.toFixed(2)} MW
      </text>

      <rect className={`node-box ${failed("battery") ? "failed" : ""}`} x="40" y="180" width="140" height="64" />
      <text className="node-label" x="52" y="202">
        BATTERY
      </text>
      <text className="node-val" x="52" y="226">
        {(s.battery_soc * 100).toFixed(0)}%  {s.battery_power_mw >= 0 ? "DIS" : "CHG"}
      </text>

      <rect className={`node-box ${failed("electrolyser") ? "failed" : ""}`} x="310" y="50" width="170" height="72" />
      <text className="node-label" x="322" y="72">
        ELECTROLYSER
      </text>
      <text className="node-val" x="322" y="96">
        {s.electrolyser_power_mw.toFixed(2)} MW
      </text>
      <text className="node-val" x="322" y="112">
        {s.hydrogen_rate_kgph.toFixed(0)} kg/h  {s.electrolyser_status}
      </text>

      <rect className={`node-box ${failed("co2_capture") ? "failed" : ""}`} x="560" y="180" width="150" height="64" />
      <text className="node-label" x="572" y="202">
        CO2 CAPTURE
      </text>
      <text className="node-val" x="572" y="226">
        {s.co2_rate_kgph.toFixed(0)} kg/h
      </text>

      <rect className={`node-box ${failed("methanation") ? "failed" : ""}`} x="310" y="250" width="170" height="72" />
      <text className="node-label" x="322" y="272">
        METHANATION
      </text>
      <text className="node-val" x="322" y="296">
        {s.methane_rate_kgph.toFixed(0)} kg/h
      </text>
      <text className="node-val" x="322" y="312">
        T {s.methanation_temperature_c.toFixed(0)}°C
      </text>

      <rect className="node-box" x="310" y="360" width="170" height="44" />
      <text className="node-label" x="322" y="378">
        SYNTHETIC CH4
      </text>
      <text className="node-val" x="322" y="396">
        {s.methane_total_kg.toFixed(0)} kg total
      </text>

      <path className={`${on(s.solar_power_mw)} power`} d="M180 82 H310" />
      <path className={`${on(Math.abs(s.battery_power_mw))} power`} d="M110 180 V114" />
      <path className={`${on(s.hydrogen_rate_kgph)} h2`} d="M395 122 V250" />
      <path className={`${on(s.co2_rate_kgph)} co2`} d="M560 212 H480" />
      <path className={`${on(s.methane_rate_kgph)} ch4`} d="M395 322 V360" />
      <path className={`${on(s.plant_load_mw)} power`} d="M180 212 H310 212 250" />
    </svg>
  );
}

function Health({ label, value }: { label: string; value: number }) {
  const cls = value < 0.7 ? "fault" : value < 0.9 ? "warn" : "";
  return (
    <div>
      <div className="health-row">
        <span>{label}</span>
        <span>{(value * 100).toFixed(0)}%</span>
      </div>
      <div className={`bar ${cls}`}>
        <span style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
      </div>
    </div>
  );
}

export default function App() {
  const [scenario, setScenario] = useState("storm");
  const [data, setData] = useState<ComparePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [ctrlView, setCtrlView] = useState<"mpc" | "rules" | "naive">("mpc");

  const load = async () => {
    setBusy(true);
    setErr(null);
    try {
      const payload = await compareSimulation(scenario, scenario === "storm" ? 7 : undefined);
      setData(payload);
      setIdx(0);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const series = data?.timeseries[ctrlView] ?? [];
  const s: Reality | undefined = series[Math.min(idx, Math.max(series.length - 1, 0))];
  const events: EventRow[] = data?.full_events[ctrlView] ?? [];

  useEffect(() => {
    if (!playing || !series.length) return;
    const t = window.setInterval(() => {
      setIdx((i) => (i + 1) % series.length);
    }, 180);
    return () => window.clearInterval(t);
  }, [playing, series.length]);

  const visibleEvents = useMemo(() => {
    const hour = s?.hour ?? 0;
    return events.filter((e) => e.hour <= hour).slice(-12).reverse();
  }, [events, s?.hour]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>PLANTOS</h1>
          <span>Autonomous Operations Center</span>
        </div>
        <div className={`mode-pill ${modeClass(s?.plant_mode ?? "NORMAL")}`}>
          {s ? `STATUS  ${s.plant_mode}` : "OFFLINE"}
        </div>
        <div className="clock">{s ? fmtHour(s.hour) : "--"}</div>
        <div className="controls">
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            <option value="storm">STORM TEST</option>
            <option value="cascade">CASCADE TEST</option>
            <option value="baseline">BASELINE</option>
          </select>
          <select value={ctrlView} onChange={(e) => setCtrlView(e.target.value as typeof ctrlView)}>
            <option value="mpc">VIEW: PLANTOS MPC</option>
            <option value="rules">VIEW: RULES</option>
            <option value="naive">VIEW: NAIVE</option>
          </select>
          <input
            className="slider"
            type="range"
            min={0}
            max={Math.max(series.length - 1, 0)}
            value={idx}
            onChange={(e) => setIdx(Number(e.target.value))}
          />
          <button onClick={() => setPlaying((p) => !p)}>{playing ? "PAUSE" : "PLAY"}</button>
          <button className="primary" disabled={busy} onClick={() => void load()}>
            {busy ? "RUNNING…" : "RUN COMPARE"}
          </button>
        </div>
      </header>
      {err && <div className="err">{err}</div>}
      {busy && <div className="busy">Executing closed-loop simulations (naive / rules / MPC). This is live computation, not a canned demo.</div>}

      {s && data && (
        <div className="grid">
          <div className="kpis">
            <div className="kpi">
              <div className="lbl">Solar</div>
              <div className="val" style={{ color: "var(--power)" }}>
                {s.solar_power_mw.toFixed(2)}
              </div>
              <div className="sub">MW  avail {s.solar_available_mw.toFixed(2)}</div>
            </div>
            <div className="kpi">
              <div className="lbl">Battery</div>
              <div className="val">{(s.battery_soc * 100).toFixed(0)}%</div>
              <div className="sub">SOH {(s.battery_soh * 100).toFixed(1)}%</div>
            </div>
            <div className="kpi">
              <div className="lbl">Plant load</div>
              <div className="val">{s.plant_load_mw.toFixed(2)}</div>
              <div className="sub">MW</div>
            </div>
            <div className="kpi">
              <div className="lbl">Methane</div>
              <div className="val" style={{ color: "var(--ch4)" }}>
                {s.methane_rate_kgph.toFixed(0)}
              </div>
              <div className="sub">kg/h</div>
            </div>
            <div className="kpi">
              <div className="lbl">Hydrogen</div>
              <div className="val" style={{ color: "var(--h2)" }}>
                {s.hydrogen_rate_kgph.toFixed(0)}
              </div>
              <div className="sub">kg/h  store {s.h2_stored_kg.toFixed(0)} kg</div>
            </div>
            <div className="kpi">
              <div className="lbl">Curtailment</div>
              <div className="val">{s.curtailed_power_mw.toFixed(2)}</div>
              <div className="sub">MW</div>
            </div>
            <div className="kpi">
              <div className="lbl">GHI</div>
              <div className="val">{s.irradiance_wm2.toFixed(0)}</div>
              <div className="sub">W/m²  {s.ambient_temp_c.toFixed(1)}°C</div>
            </div>
            <div className="kpi">
              <div className="lbl">Survival</div>
              <div className="val">{data.controllers[ctrlView].survival_score.toFixed(3)}</div>
              <div className="sub">run metric, not a claim</div>
            </div>
          </div>

          <div className="panel">
            <h2>Equipment health</h2>
            <div className="body">
              <Health label="Electrolyser" value={s.electrolyser_health} />
              <Health label="Battery SOH" value={s.battery_soh} />
              <Health label="CO2 capture" value={s.co2_capture_health} />
              <Health label="Methanation" value={s.methanation_health} />
              <div style={{ marginTop: 16, color: "var(--muted)", fontSize: 11 }}>
                Isolated: {s.isolated_components?.length ? s.isolated_components.join(", ") : "none"}
              </div>
              <div style={{ marginTop: 8, color: "var(--warn)", fontSize: 12 }}>
                {(s.active_faults || [])
                  .filter((f) => f.active)
                  .map((f) => `${f.fault_type} (${f.component}, sev ${f.severity.toFixed(2)})`)
                  .join(" · ") || "No injected faults this hour"}
              </div>
            </div>
          </div>

          <div className="panel">
            <h2>Live plant</h2>
            <div className="body schematic">
              <PlantSchematic s={s} />
            </div>
          </div>

          <div className="panel">
            <h2>Decision timeline</h2>
            <div className="body timeline">
              {visibleEvents.map((e, i) => (
                <div className="tl-item" key={`${e.hour}-${e.reason_code}-${i}`}>
                  <div className="t">{fmtHour(e.hour)}</div>
                  <div>
                    <div className="code">{e.reason_code}</div>
                    <p>{e.explanation}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel" style={{ gridColumn: "1 / 3" }}>
            <h2>Methane rate — {ctrlView}</h2>
            <div className="legend">
              <span>
                <i style={{ background: "#e8c547" }} />
                CH4 kg/h
              </span>
              <span>
                <i style={{ background: "#4fc3f7" }} />
                Solar MW (scaled)
              </span>
            </div>
            <Spark series={series.map((r) => r.methane_rate_kgph)} color="#e8c547" />
          </div>

          <div className="panel">
            <h2>Controller comparison</h2>
            <div className="body">
              <table className="table">
                <thead>
                  <tr>
                    <th></th>
                    <th>Naive</th>
                    <th>Rules</th>
                    <th>PlantOS</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["Methane kg", "methane_total_kg", 1],
                      ["Curtail %", "curtailment_fraction", 100],
                      ["Downtime h", "downtime_hours", 1],
                      ["Survival", "survival_score", 1],
                      ["Min SOC", "min_soc", 100],
                    ] as const
                  ).map(([label, key, scale]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      {(["naive", "rules", "mpc"] as const).map((c) => {
                        const v = data.controllers[c][key] * scale;
                        const best =
                          key === "curtailment_fraction" || key === "downtime_hours"
                            ? Math.min(
                                data.controllers.naive[key],
                                data.controllers.rules[key],
                                data.controllers.mpc[key]
                              ) === data.controllers[c][key]
                            : Math.max(
                                data.controllers.naive[key],
                                data.controllers.rules[key],
                                data.controllers.mpc[key]
                              ) === data.controllers[c][key];
                        return (
                          <td key={c} className={best ? "hi" : ""}>
                            {v.toFixed(key === "survival_score" ? 3 : 1)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="cf" style={{ marginTop: 12 }}>
                <div>
                  <h3>Without PlantOS (naive)</h3>
                  <ul>
                    <li>Methane {data.counterfactual.without.methane_total_kg.toFixed(0)} kg</li>
                    <li>Downtime {data.counterfactual.without.downtime_hours.toFixed(1)} h</li>
                    <li>Curtail {(100 * data.counterfactual.without.curtailment_fraction).toFixed(1)}%</li>
                  </ul>
                </div>
                <div>
                  <h3>With PlantOS (MPC)</h3>
                  <ul>
                    <li>Methane {data.counterfactual.with.methane_total_kg.toFixed(0)} kg</li>
                    <li>Downtime {data.counterfactual.with.downtime_hours.toFixed(1)} h</li>
                    <li>Curtail {(100 * data.counterfactual.with.curtailment_fraction).toFixed(1)}%</li>
                  </ul>
                  <div className="saved">
                    Δ methane {data.counterfactual.methane_saved_kg.toFixed(0)} kg · downtime avoided{" "}
                    {data.counterfactual.downtime_avoided_hours.toFixed(1)} h
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
