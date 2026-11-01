import { useEffect, useState } from "react";
import { api } from "../api";
import type { MachineDesign, Mechanism, StationTiming, TimingBar, TimingResult, TimingRow, TimingWarning } from "../types";
import { reasonText, seconds, signedSeconds, WARNING_LABEL, warningText } from "./timingText";

// The Timing tab (Phase 2, section I). It shows the timing engine's result for the revision being
// viewed (GET /projects/{id}/timing) and computes nothing itself: cycle, margin, limiting step,
// status and every bar's start and end come from the result (rule 2). The diagram is SVG drawn here,
// no chart library.

type Status = "meets" | "misses" | "no_target" | "not_computable";

/** Read from the result only: the UI never compares the cycle with the target itself. */
function statusOf(st: StationTiming): Status {
  if (st.not_computable.length > 0) return "not_computable";
  if (st.target_cycle_time_s === null) return "no_target";
  return st.warnings.some((w) => w.code === "target_not_met") ? "misses" : "meets";
}

const STATUS: Record<Status, { label: string; className: string }> = {
  meets: { label: "meets target", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" },
  misses: { label: "misses target", className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" },
  no_target: { label: "no target", className: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  not_computable: { label: "not computable", className: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300" },
};

/** A station with no steps, no target and no warning has nothing to show (frame, cabinet, ...): one line, not a
 * row. A warning (a mechanism out of catalog bounds) keeps the station in the panel and the list. */
const untimed = (st: StationTiming) =>
  st.target_cycle_time_s === null &&
  st.warnings.length === 0 &&
  st.not_computable.length === 1 &&
  st.not_computable[0].code === "no_steps";

const Pill = ({ className, children }: { className: string; children: string }) => (
  <span className={`mr-2 inline-block rounded px-1.5 py-0.5 text-[11px] ${className}`}>{children}</span>
);

// --- Diagram -------------------------------------------------------------------------------------

const GUTTER = 170; // row labels
const PLOT = 600;
const RIGHT = 100; // room for the target label when the target sits at the axis end
const ROW = 26;
const CHAR = 6.8; // width of one 11px monospace character, to decide whether a label fits in its bar
const TOP = 18;

/** A round tick step giving at most 8 intervals, and the axis end: the next tick at or after `t`. */
function axis(t: number): { step: number; end: number } {
  const span = Math.max(t, 1e-3);
  const magnitude = 10 ** Math.floor(Math.log10(span / 8));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => span / s <= 8)!;
  return { step, end: Math.ceil(span / step - 1e-9) * step };
}

function unit(m: Mechanism, linear: string, rotary: string): string {
  return m.kind === "linear" ? linear : rotary;
}

/** Hover text: where the bar's number comes from (model fields, or the step's own duration). */
function barSource(bar: TimingBar, row: TimingRow, mechanisms: Mechanism[]): string {
  const head = `${bar.step_id} · ${seconds(bar.duration_s)} (${seconds(bar.start_s)} → ${seconds(bar.end_s)})`;
  const path = bar.critical ? "on the critical path" : "not on the critical path";
  const m = row.kind === "mechanism" ? mechanisms.find((x) => x.id === row.id) : undefined;
  if (bar.source === "fixed") return `${head}\nfixed duration: the step's duration\n${path}`;
  if (!m) return `${head}\n${bar.source} profile, mechanism ${row.id} (not in this revision's design)\n${path}`;
  const inputs = [
    `stroke ${m.stroke} ${unit(m, "mm", "deg")}`,
    `max speed ${m.max_speed} ${unit(m, "mm/s", "deg/s")}`,
    `acceleration ${m.acceleration} ${unit(m, "mm/s²", "deg/s²")}`,
    ...(bar.source === "s_curve" ? [`jerk ${m.jerk} ${unit(m, "mm/s³", "deg/s³")}`] : []),
    ...(m.dwell_s !== null ? [`dwell ${m.dwell_s} s`] : []),
  ];
  const profile = bar.source === "s_curve" ? "S-curve" : "trapezoidal";
  return `${head}\n${profile} profile, mechanism ${m.id}: ${inputs.join(", ")}\n${path}`;
}

function Diagram({ st, mechanisms }: { st: StationTiming; mechanisms: Mechanism[] }) {
  const sid = st.station_id;
  const cycle = st.cycle_time_s!;
  const target = st.target_cycle_time_s;
  const { step, end } = axis(Math.max(cycle, target ?? 0));
  const x = (t: number) => GUTTER + (t / end) * PLOT;
  const decimals = Math.max(0, -Math.floor(Math.log10(step) + 1e-9));

  let y = TOP;
  const rows = st.diagram.map((row) => {
    const top = y;
    let cursor = -Infinity;
    let below = false;
    const bars = row.bars.map((bar) => {
      const x0 = x(bar.start_s);
      const x1 = x(bar.end_s);
      const text = `${bar.step_id} · ${seconds(bar.duration_s)}`;
      const inside = text.length * CHAR + 8 <= x1 - x0;
      // A label that does not fit goes under its bar, pushed right of the previous one.
      const lx = inside ? x0 + 5 : Math.max(x0, cursor + 6);
      if (!inside) {
        cursor = lx + text.length * CHAR;
        below = true;
      }
      return (
        <g key={bar.step_id}>
          <rect
            data-testid={`timing-bar-${sid}-${bar.step_id}`}
            data-critical={bar.critical}
            data-start-s={bar.start_s}
            data-end-s={bar.end_s}
            x={x0}
            y={top + 4}
            width={x1 - x0}
            height={ROW - 6}
            className={bar.critical ? "fill-amber-500" : "fill-slate-300 dark:fill-slate-600"}
          >
            <title>{barSource(bar, row, mechanisms)}</title>
          </rect>
          <text
            x={lx}
            y={inside ? top + 18 : top + ROW + 10}
            className="pointer-events-none fill-slate-800 font-mono text-[11px] dark:fill-slate-200"
          >
            {text}
          </text>
        </g>
      );
    });
    y += ROW + (below ? 14 : 6);
    return (
      <g key={`${row.kind}-${row.id}`}>
        <text x={GUTTER - 8} y={top + 15} textAnchor="end" className="fill-slate-700 font-mono text-[11px] dark:fill-slate-300">
          {row.id}
        </text>
        <text x={GUTTER - 8} y={top + 26} textAnchor="end" className="fill-slate-400 text-[10px]">
          {row.kind === "mechanism" ? "mechanism" : "fixed step"}
        </text>
        {bars}
      </g>
    );
  });

  const axisY = y;
  const ticks = Array.from({ length: Math.round(end / step) + 1 }, (_, i) => i * step);
  // The later of the two lines is labelled on its right, the earlier on its left, so they never overlap.
  const targetLater = target !== null && target >= cycle;
  const lines: { key: string; t: number; label: string; right: boolean; className: string; dashed: boolean }[] = [
    { key: "cycle", t: cycle, label: `cycle ${seconds(cycle)}`, right: !targetLater, className: "stroke-slate-900 dark:stroke-slate-100", dashed: false },
  ];
  if (target !== null) {
    lines.push({ key: "target", t: target, label: `target ${seconds(target)}`, right: targetLater, className: "stroke-red-600", dashed: true });
  }

  return (
    <div className="overflow-x-auto">
      <svg width={GUTTER + PLOT + RIGHT} height={axisY + 26} data-testid={`timing-diagram-${sid}`} className="text-[10px]">
        {/* Cycle and target lines first, so bars and labels are drawn over them. */}
        {lines.map((l) => (
          <g key={l.key}>
            <line
              data-testid={`timing-${l.key}-line-${sid}`}
              x1={x(l.t)}
              x2={x(l.t)}
              y1={10}
              y2={axisY}
              strokeWidth={1.5}
              strokeDasharray={l.dashed ? "4 3" : undefined}
              className={l.className}
            />
            <text
              x={x(l.t) + (l.right ? 4 : -4)}
              y={9}
              textAnchor={l.right ? "start" : "end"}
              className={l.key === "target" ? "fill-red-600" : "fill-slate-900 dark:fill-slate-100"}
            >
              {l.label}
            </text>
          </g>
        ))}
        {rows}
        <line x1={GUTTER} x2={GUTTER + PLOT} y1={axisY} y2={axisY} className="stroke-slate-400" />
        {ticks.map((t, i) => (
          <g key={i}>
            <line
              data-testid={i === 0 ? `timing-axis-zero-${sid}` : i === ticks.length - 1 ? `timing-axis-end-${sid}` : undefined}
              data-time-s={t}
              x1={x(t)}
              x2={x(t)}
              y1={axisY}
              y2={axisY + 5}
              className="stroke-slate-400"
            />
            <text x={x(t)} y={axisY + 17} textAnchor="middle" className="fill-slate-500">
              {t.toFixed(decimals)}
            </text>
          </g>
        ))}
        <text x={GUTTER + PLOT + 10} y={axisY + 17} className="fill-slate-500">
          s
        </text>
      </svg>
    </div>
  );
}

// --- Panels --------------------------------------------------------------------------------------

function WarningItem({ testId, w, design }: { testId: string; w: TimingWarning; design: MachineDesign }) {
  const linked = w.source_url && /^https?:\/\//.test(w.source_url);
  return (
    <li data-testid={testId}>
      <Pill className={STATUS.misses.className}>{WARNING_LABEL[w.code]}</Pill>
      {warningText(w, design)}
      {w.source_title && (
        <>
          {" · "}
          {linked ? (
            <a className="text-amber-700 underline dark:text-amber-400" href={w.source_url!} target="_blank" rel="noreferrer">
              {w.source_title}
            </a>
          ) : (
            w.source_title
          )}
        </>
      )}
    </li>
  );
}

export default function TimingView({ projectId, revision, design }: { projectId: string; revision: number; design: MachineDesign }) {
  const [result, setResult] = useState<TimingResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let obsolete = false;
    setResult(null);
    setError(null);
    api.timing(projectId, revision)
      .then((next) => { if (!obsolete) setResult(next); })
      .catch((e: Error) => { if (!obsolete) setError(e.message); });
    // A response for a revision no longer shown must not replace the current one.
    return () => { obsolete = true; };
  }, [projectId, revision]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!result) return <p className="text-sm text-slate-500">Computing the timing…</p>;

  const stationOf = (sid: string) => design.stations.find((s) => s.id === sid);
  const shown = result.stations.filter((st) => !untimed(st));
  const skipped = result.stations.filter(untimed);
  const timed = result.stations.filter((st) => st.cycle_time_s !== null);
  const warningGroups = shown.filter((st) => st.warnings.length > 0 || st.not_computable.length > 0);
  const noWarnings = warningGroups.length === 0 && result.warnings.length === 0;

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">
        Computed by the timing engine from each station's mechanisms and steps, with no AI call. Times are rounded to
        the millisecond; hover a bar to see where its time comes from.
      </p>

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Cycle-time check</h2>
        <table className="w-full text-sm" data-testid="timing-check">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500 dark:border-slate-800">
              <th className="py-1 pr-3 font-medium">Station</th>
              <th className="py-1 pr-3 font-medium">Target</th>
              <th className="py-1 pr-3 font-medium">Computed</th>
              <th className="py-1 pr-3 font-medium">Margin</th>
              <th className="py-1 pr-3 font-medium">Limiting step</th>
              <th className="py-1 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((st) => {
              const status = statusOf(st);
              return (
                <tr
                  key={st.station_id}
                  data-testid={`timing-check-${st.station_id}`}
                  data-status={status}
                  className="border-b border-slate-100 align-top dark:border-slate-800/60"
                >
                  <td className="py-1.5 pr-3">
                    <div>{stationOf(st.station_id)?.name}</div>
                    <div className="font-mono text-xs text-slate-400">{st.station_id}</div>
                  </td>
                  <td className="py-1.5 pr-3">{st.target_cycle_time_s === null ? "—" : seconds(st.target_cycle_time_s)}</td>
                  <td className="py-1.5 pr-3">{st.cycle_time_s === null ? "—" : seconds(st.cycle_time_s)}</td>
                  <td className="py-1.5 pr-3">{st.margin_s === null ? "—" : signedSeconds(st.margin_s)}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{st.limiting_step_id ?? "—"}</td>
                  <td className="py-1.5">
                    <Pill className={STATUS[status].className}>{STATUS[status].label}</Pill>
                    {st.not_computable.length > 0 && (
                      <div className="text-xs text-slate-500">{st.not_computable.map(reasonText).join("; ")}</div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {skipped.length > 0 && (
          <p className="mt-2 text-xs text-slate-400">
            No steps and no target, so not timed:{" "}
            {skipped.map((st, i) => (
              <span key={st.station_id}>
                {i > 0 && ", "}
                {stationOf(st.station_id)?.name} <span className="font-mono">{st.station_id}</span>
              </span>
            ))}
          </p>
        )}
      </section>

      <section className="card p-4" data-testid="timing-warnings">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Warnings</h2>
        {noWarnings && <p className="text-sm text-slate-500">No warnings.</p>}
        <div className="space-y-2 text-sm">
          {warningGroups.map((st) => (
            <div key={st.station_id}>
              <div>
                {stationOf(st.station_id)?.name} <span className="font-mono text-xs text-slate-400">{st.station_id}</span>
              </div>
              <ul className="ml-4 space-y-0.5">
                {st.warnings.map((w, i) => (
                  <WarningItem key={i} testId={`timing-warning-${st.station_id}-${w.code}`} w={w} design={design} />
                ))}
                {st.not_computable.map((r, i) => (
                  <li key={`nc-${i}`} data-testid={`timing-warning-${st.station_id}-not_computable-${r.code}`}>
                    <Pill className={STATUS.not_computable.className}>not computable</Pill>
                    {reasonText(r)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {result.warnings.length > 0 && (
            <div>
              <div>Line (transports)</div>
              <ul className="ml-4 space-y-0.5">
                {result.warnings.map((w, i) => (
                  <WarningItem key={i} testId={`timing-warning-line-${w.code}`} w={w} design={design} />
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <h2 className="text-sm font-semibold text-slate-500">Timing diagrams</h2>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <i className="inline-block h-2.5 w-3 bg-amber-500" /> on the critical path
          </span>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <i className="inline-block h-2.5 w-3 bg-slate-300 dark:bg-slate-600" /> not on the critical path
          </span>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <i className="inline-block h-0.5 w-3 bg-slate-900 dark:bg-slate-100" /> computed cycle
          </span>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <i className="inline-block w-3 border-t-2 border-dashed border-red-600" /> target
          </span>
        </div>
        {timed.length === 0 && <p className="text-sm text-slate-500">No station has a computed cycle time yet.</p>}
        {timed.map((st) => (
          <div key={st.station_id} className="card p-4">
            <div className="mb-1 flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium">{stationOf(st.station_id)?.name}</span>
              <span className="font-mono text-xs text-slate-400">{st.station_id}</span>
              <span
                className="ml-auto text-xs"
                data-testid={`timing-cycle-readout-${st.station_id}`}
                data-value-s={st.cycle_time_s!}
              >
                cycle <b>{seconds(st.cycle_time_s!)}</b> · limiting{" "}
                <span className="font-mono">{st.limiting_step_id}</span>
              </span>
            </div>
            <Diagram st={st} mechanisms={stationOf(st.station_id)?.mechanisms ?? []} />
          </div>
        ))}
      </section>
    </div>
  );
}
