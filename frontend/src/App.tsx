/**
 * PlantOS operations console.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2026 TeslaNeuro
 */
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

const fmtNum = (n: number, digits = 1) =>
  n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });

const battVerb = (p: number) => {
  if (p > 0.05) return "DISCHARGE";
  if (p < -0.05) return "CHARGE";
  return "IDLE";
};

const pretty = (s: string) => s.replaceAll("_", " ");

function Spark({
  methane,
  solar,
  idx,
}: {
  methane: number[];
  solar: number[];
  idx: number;
}) {
  const w = 640;
  const h = 168;
  const padL = 8;
  const padR = 8;
  const padT = 10;
  const padB = 22;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const n = Math.max(methane.length - 1, 1);
  const maxM = Math.max(...methane, 1e-6);
  const maxS = Math.max(...solar, 1e-6);
  const xAt = (i: number) => padL + (i / n) * innerW;
  const yM = (v: number) => padT + innerH - (v / maxM) * innerH;
  const yS = (v: number) => padT + innerH - (v / maxS) * innerH;
  const poly = (series: number[], y: (v: number) => number) =>
    series.map((v, i) => `${xAt(i)},${y(v)}`).join(" ");
  const playX = xAt(Math.min(idx, Math.max(methane.length - 1, 0)));
  const days = Math.ceil(methane.length / 24);
  const ticks = Array.from({ length: days }, (_, d) => d * 24).filter((i) => i < methane.length);

  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Methane and solar over the run">
      {ticks.map((i) => (
        <g key={i}>
          <line className="chart-grid" x1={xAt(i)} y1={padT} x2={xAt(i)} y2={padT + innerH} />
          <text className="chart-tick" x={xAt(i) + 4} y={h - 6}>
            D{Math.floor(i / 24) + 1}
          </text>
        </g>
      ))}
      <line className="chart-grid" x1={padL} y1={padT + innerH} x2={w - padR} y2={padT + innerH} />
      <text className="chart-axis ch4" x={padL + 255} y={padT - 2}>
        {maxM.toFixed(0)} kg/h
      </text>
      <text className="chart-axis solar" x={w - padR - 255} y={padT - 2} textAnchor="end">
        {maxS.toFixed(1)} MW
      </text>
      <polyline className="spark-solar" fill="none" stroke="#4fc3f7" strokeWidth="1.8" points={poly(solar, yS)} />
      <polyline className="spark-ch4" fill="none" stroke="#e8c547" strokeWidth="2.2" points={poly(methane, yM)} />
      <line className="playhead" x1={playX} y1={padT} x2={playX} y2={padT + innerH} />
    </svg>
  );
}

function NodeBox({
  x,
  y,
  w,
  h,
  title,
  lines,
  failed,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  lines: string[];
  failed?: boolean;
}) {
  return (
    <g>
      <rect className={`node-box ${failed ? "failed" : ""}`} x={x} y={y} width={w} height={h} rx="6" />
      <text className={`node-label ${failed ? "failed" : ""}`} x={x + 16} y={y + 26}>
        {title}
        {failed ? "  FAULT" : ""}
      </text>
      {lines.map((line, i) => (
        <text key={i} className="node-val" x={x + 16} y={y + 52 + i * 22}>
          {line}
        </text>
      ))}
    </g>
  );
}

function PlantSchematic({ s }: { s: Reality }) {
  const iso = new Set(s.isolated_components || []);
  const failed = (name: string) => iso.has(name) || (s.active_faults || []).some((f) => f.component === name && f.active);
  const on = (p: number) => (p > 0.15 ? "flow" : "flow off");
  return (
    <svg className="plant" viewBox="0 0 860 500" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Plant power and material path">
      <defs>
        <marker id="arr-power" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#4fc3f7" />
        </marker>
        <marker id="arr-h2" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#7ee0ff" />
        </marker>
        <marker id="arr-ch4" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#e8c547" />
        </marker>
        <marker id="arr-co2" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#b39ddb" />
        </marker>
      </defs>

      <text className="schematic-kicker" x="28" y="30">
        Power and material path
      </text>
      <g className="schematic-legend">
        <line className="flow power" x1="400" y1="24" x2="432" y2="24" />
        <text x="440" y="29">
          Power
        </text>
        <line className="flow h2" x1="520" y1="24" x2="552" y2="24" />
        <text x="560" y="29">
          H₂
        </text>
        <line className="flow co2" x1="610" y1="24" x2="642" y2="24" />
        <text x="650" y="29">
          CO₂
        </text>
        <line className="flow ch4" x1="710" y1="24" x2="742" y2="24" />
        <text x="750" y="29">
          CH₄
        </text>
      </g>

      <NodeBox
        x={24}
        y={52}
        w={220}
        h={110}
        title="SOLAR PV"
        failed={failed("solar")}
        lines={[`${s.solar_power_mw.toFixed(2)} MW`, `avail ${s.solar_available_mw.toFixed(2)} MW`]}
      />
      <NodeBox
        x={24}
        y={230}
        w={220}
        h={110}
        title="BATTERY"
        failed={failed("battery")}
        lines={[`${(s.battery_soc * 100).toFixed(0)}% SOC  ${battVerb(s.battery_power_mw)}`, `${s.battery_power_mw >= 0 ? "+" : ""}${s.battery_power_mw.toFixed(2)} MW`]}
      />
      <NodeBox
        x={330}
        y={48}
        w={250}
        h={120}
        title="ELECTROLYSER"
        failed={failed("electrolyser")}
        lines={[
          `${s.electrolyser_power_mw.toFixed(2)} MW  ${s.electrolyser_status}`,
          `${s.hydrogen_rate_kgph.toFixed(0)} kg/h H₂`,
        ]}
      />
      <NodeBox
        x={640}
        y={230}
        w={196}
        h={110}
        title="CO₂ CAPTURE"
        failed={failed("co2_capture")}
        lines={[`${s.co2_rate_kgph.toFixed(0)} kg/h`, `${s.co2_capture_power_mw.toFixed(2)} MW`]}
      />
      <NodeBox
        x={330}
        y={260}
        w={250}
        h={120}
        title="METHANATION"
        failed={failed("methanation")}
        lines={[`${s.methane_rate_kgph.toFixed(0)} kg/h CH₄`, `T ${s.methanation_temperature_c.toFixed(0)}°C`]}
      />
      <NodeBox
        x={330}
        y={412}
        w={250}
        h={72}
        title="SYNTHETIC CH₄"
        lines={[`${fmtNum(s.methane_total_kg, 0)} kg total`]}
      />

      <path className={`${on(s.solar_power_mw)} power`} markerEnd="url(#arr-power)" d="M244 107 H330" />
      <path
        className={`${on(Math.abs(s.battery_power_mw))} power`}
        markerEnd="url(#arr-power)"
        d={s.battery_power_mw >= 0 ? "M134 230 V162" : "M134 162 V230"}
      />
      <path className={`${on(s.plant_load_mw)} power`} markerEnd="url(#arr-power)" d="M244 285 H290 V320 H330" />
      <path className={`${on(s.hydrogen_rate_kgph)} h2`} markerEnd="url(#arr-h2)" d="M455 168 V260" />
      <path className={`${on(s.co2_rate_kgph)} co2`} markerEnd="url(#arr-co2)" d="M640 285 H590 V320 H580" />
      <path className={`${on(s.methane_rate_kgph)} ch4`} markerEnd="url(#arr-ch4)" d="M455 380 V412" />
    </svg>
  );
}

function Health({ label, value }: { label: string; value: number }) {
  const cls = value < 0.7 ? "fault" : value < 0.9 ? "warn" : "";
  return (
    <div className="health">
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

  const load = async (name = scenario) => {
    setBusy(true);
    setPlaying(false);
    setErr(null);
    try {
      const payload = await compareSimulation(name, name === "storm" ? 7 : undefined);
      setData(payload);
      setIdx(0);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load(scenario);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const series = data?.timeseries[ctrlView] ?? [];
  const last = Math.max(series.length - 1, 0);
  const safeIdx = Math.min(idx, last);
  const s: Reality | undefined = series[safeIdx];
  const events: EventRow[] = data?.full_events[ctrlView] ?? [];

  useEffect(() => {
    if (idx > last) setIdx(last);
  }, [idx, last]);

  useEffect(() => {
    if (!playing || !series.length) return;
    const t = window.setInterval(() => {
      setIdx((i) => (i + 1) % series.length);
    }, 180);
    return () => window.clearInterval(t);
  }, [playing, series.length]);

  const visibleEvents = useMemo(() => {
    const hour = s?.hour ?? 0;
    return events.filter((e) => e.hour <= hour).slice(-16).reverse();
  }, [events, s?.hour]);

  const activeFaults = (s?.active_faults || []).filter((f) => f.active);
  const viewLabel = ctrlView === "mpc" ? "PlantOS MPC" : ctrlView === "rules" ? "Rules" : "Naive";
  const stale = data && data.scenario !== scenario;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>PLANTOS</h1>
          <span>Autonomous Operations Center</span>
        </div>
        <div className={`mode-pill ${modeClass(s?.plant_mode ?? "NORMAL")}`}>
          <i />
          {s ? pretty(s.plant_mode) : "OFFLINE"}
        </div>
        <div className="clock">
          <span className="clock-lbl">Sim time</span>
          <strong>{s ? fmtHour(s.hour) : "--"}</strong>
        </div>
        <div className="controls">
          <label>
            Scenario
            <select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={busy}>
              <option value="storm">Storm test</option>
              <option value="cascade">Cascade test</option>
              <option value="baseline">Baseline</option>
            </select>
          </label>
          <label>
            Controller
            <select value={ctrlView} onChange={(e) => setCtrlView(e.target.value as typeof ctrlView)}>
              <option value="mpc">PlantOS MPC</option>
              <option value="rules">Rules</option>
              <option value="naive">Naive</option>
            </select>
          </label>
          <label>
            Simulation
            <button className="primary" disabled={busy} onClick={() => void load()}>
              {busy ? "Running…" : "Run compare"}
            </button>
          </label>
        </div>
      </header>

      <div className="transport">
        <button className="play" onClick={() => setPlaying((p) => !p)} disabled={!series.length || busy}>
          {playing ? "Pause" : "Play"}
        </button>
        <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={!series.length}>
          -1 h
        </button>
        <input
          className="slider"
          type="range"
          min={0}
          max={last}
          value={safeIdx}
          aria-label="Simulation hour"
          onChange={(e) => {
            setPlaying(false);
            setIdx(Number(e.target.value));
          }}
        />
        <button onClick={() => setIdx((i) => Math.min(last, i + 1))} disabled={!series.length}>
          +1 h
        </button>
        <div className="transport-meta">
          {series.length ? (
            <>
              Hour {Math.round(s?.hour ?? safeIdx)} / {last}
              <span>
                {fmtHour(0)} – {fmtHour(last)}
              </span>
            </>
          ) : (
            "No run loaded"
          )}
        </div>
      </div>

      {err && <div className="err">{err}</div>}
      {busy && (
        <div className="busy">
          Executing closed-loop simulations (naive / rules / MPC). This is live computation, not a canned demo.
        </div>
      )}
      {stale && !busy && (
        <div className="busy">Loaded run is {data.scenario}. Scenario dropdown is {scenario} — run compare to refresh.</div>
      )}

      {busy && !data && (
        <div className="splash">
          <div className="splash-card">Running live controller comparison…</div>
        </div>
      )}

      {s && data && (
        <div className="workspace">
          <div className="kpis">
            <div className="kpi">
              <div className="lbl">Solar</div>
              <div className="val" style={{ color: "var(--power)" }}>
                {s.solar_power_mw.toFixed(2)} <small>MW</small>
              </div>
              <div className="sub">Available {s.solar_available_mw.toFixed(2)} MW</div>
            </div>
            <div className="kpi">
              <div className="lbl">Battery</div>
              <div className="val">{(s.battery_soc * 100).toFixed(0)}%</div>
              <div className="sub">
                {battVerb(s.battery_power_mw)} · SOH {(s.battery_soh * 100).toFixed(1)}%
              </div>
            </div>
            <div className="kpi">
              <div className="lbl">Plant load</div>
              <div className="val">
                {s.plant_load_mw.toFixed(2)} <small>MW</small>
              </div>
              <div className="sub">Electrical demand</div>
            </div>
            <div className="kpi">
              <div className="lbl">Methane</div>
              <div className="val" style={{ color: "var(--ch4)" }}>
                {fmtNum(s.methane_rate_kgph, 0)} <small>kg/h</small>
              </div>
              <div className="sub">Total {fmtNum(s.methane_total_kg, 0)} kg</div>
            </div>
            <div className="kpi">
              <div className="lbl">Hydrogen</div>
              <div className="val" style={{ color: "var(--h2)" }}>
                {fmtNum(s.hydrogen_rate_kgph, 0)} <small>kg/h</small>
              </div>
              <div className="sub">Store {fmtNum(s.h2_stored_kg, 0)} kg</div>
            </div>
            <div className="kpi">
              <div className="lbl">Curtailment</div>
              <div className="val">
                {s.curtailed_power_mw.toFixed(2)} <small>MW</small>
              </div>
              <div className="sub">Unused solar</div>
            </div>
            <div className="kpi">
              <div className="lbl">Irradiance</div>
              <div className="val">
                {fmtNum(s.irradiance_wm2, 0)} <small>W/m²</small>
              </div>
              <div className="sub">
                {s.ambient_temp_c.toFixed(1)}°C · cloud {(s.cloud_cover * 100).toFixed(0)}%
              </div>
            </div>
            <div className="kpi">
              <div className="lbl">Survival</div>
              <div className="val">{data.controllers[ctrlView].survival_score.toFixed(3)}</div>
              <div className="sub">Run metric for this controller</div>
            </div>
          </div>

          <div className="main">
            <div className="panel">
              <h2>Health · {pretty(s.plant_mode)}</h2>
              <div className="body">
                <Health label="Electrolyser" value={s.electrolyser_health} />
                <Health label="Battery SOH" value={s.battery_soh} />
                <Health label="CO₂ capture" value={s.co2_capture_health} />
                <Health label="Methanation" value={s.methanation_health} />
                <div className={`iso-line ${s.isolated_components?.length ? "warn" : ""}`}>
                  Isolated: {s.isolated_components?.length ? s.isolated_components.join(", ") : "none"}
                </div>
                <div className={`fault-line ${activeFaults.length ? "active" : ""}`}>
                  {activeFaults.length
                    ? activeFaults.map((f) => `${pretty(f.fault_type)} · sev ${f.severity.toFixed(2)}`).join(" · ")
                    : "No active faults this hour"}
                </div>
              </div>
            </div>

            <div className="panel plant-panel">
              <h2>Live plant</h2>
              <div className="body schematic">
                <PlantSchematic s={s} />
              </div>
            </div>

            <div className="panel">
              <h2>Decision timeline</h2>
              <div className="body timeline">
                {visibleEvents.length === 0 && <div className="empty">No decisions recorded up to this hour.</div>}
                {visibleEvents.map((e, i) => {
                  const alert = /fault|emergency|fallback|infeasible/i.test(`${e.reason_code} ${e.explanation}`);
                  return (
                    <div className={`tl-item ${alert ? "alert" : ""}`} key={`${e.hour}-${e.reason_code}-${i}`}>
                      <div className="t">{fmtHour(e.hour)}</div>
                      <div>
                        <div className="code">{e.reason_code}</div>
                        <p>{e.explanation}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="bottom">
            <div className="panel">
              <h2>Methane and solar — {viewLabel}</h2>
              <div className="legend">
                <span>
                  <i style={{ background: "#e8c547" }} />
                  CH₄ {fmtNum(s.methane_rate_kgph, 0)} kg/h
                </span>
                <span>
                  <i style={{ background: "#4fc3f7" }} />
                  Solar {s.solar_power_mw.toFixed(2)} MW
                </span>
                <span className="legend-note">Each series scaled independently · line marks current hour</span>
              </div>
              <Spark
                methane={series.map((r) => r.methane_rate_kgph)}
                solar={series.map((r) => r.solar_power_mw)}
                idx={safeIdx}
              />
            </div>

            <div className="panel">
              <h2>Controller comparison</h2>
              <div className="body">
                <table className="table">
                  <thead>
                    <tr>
                      <th></th>
                      {(["naive", "rules", "mpc"] as const).map((c) => (
                        <th key={c} className={ctrlView === c ? "on" : ""}>
                          {c === "mpc" ? "PlantOS" : c === "rules" ? "Rules" : "Naive"}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["Methane kg", "methane_total_kg", 1, 0],
                        ["Curtail %", "curtailment_fraction", 100, 1],
                        ["Downtime h", "downtime_hours", 1, 1],
                        ["Survival", "survival_score", 1, 3],
                        ["Min SOC %", "min_soc", 100, 1],
                      ] as const
                    ).map(([label, key, scale, digits]) => (
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
                            <td key={c} className={`${best ? "hi" : ""} ${ctrlView === c ? "on" : ""}`}>
                              {fmtNum(v, digits)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="cf">
                  <div>
                    <h3>Without PlantOS</h3>
                    <p>
                      {fmtNum(data.counterfactual.without.methane_total_kg, 0)} kg ·{" "}
                      {fmtNum(data.counterfactual.without.downtime_hours, 1)} h down ·{" "}
                      {fmtNum(100 * data.counterfactual.without.curtailment_fraction, 1)}% curtail
                    </p>
                  </div>
                  <div>
                    <h3>With PlantOS</h3>
                    <p>
                      {fmtNum(data.counterfactual.with.methane_total_kg, 0)} kg ·{" "}
                      {fmtNum(data.counterfactual.with.downtime_hours, 1)} h down ·{" "}
                      {fmtNum(100 * data.counterfactual.with.curtailment_fraction, 1)}% curtail
                    </p>
                    <div className="saved">
                      Δ {fmtNum(data.counterfactual.methane_saved_kg, 0)} kg methane ·{" "}
                      {fmtNum(data.counterfactual.downtime_avoided_hours, 1)} h downtime avoided
                    </div>
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
