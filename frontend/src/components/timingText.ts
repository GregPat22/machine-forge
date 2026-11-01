import type { MachineDesign, NotComputableReason, TimingWarning } from "../types";

// Words for the timing engine's results, shared by the Timing tab, the model editor and the diff
// view so a reason or a warning reads the same everywhere. Everything here reads codes and ids from
// the result (rule 1); every number is the engine's (rule 2), only rounded for display.

/** Seconds with 3 decimals (milliseconds). The exact value stays in the result. */
export const seconds = (s: number) => `${s.toFixed(3)} s`;

/** A margin with its sign: + when the cycle is under the target. */
export const signedSeconds = (s: number) => `${s < 0 ? "−" : "+"}${Math.abs(s).toFixed(3)} s`;

export function reasonText(r: NotComputableReason): string {
  switch (r.code) {
    case "no_steps":
      return "no steps";
    case "duration_missing":
      return `fixed step ${r.step_id} has no duration`;
    case "mechanism_missing":
      return r.mechanism_id
        ? `motion step ${r.step_id} names mechanism ${r.mechanism_id}, which this station does not have`
        : `motion step ${r.step_id} names no mechanism`;
    case "stroke_missing":
      return `mechanism ${r.mechanism_id} has no stroke`;
    case "max_speed_missing":
      return `mechanism ${r.mechanism_id} has no max speed`;
    case "acceleration_missing":
      return `mechanism ${r.mechanism_id} has no acceleration`;
    case "jerk_missing":
      return `mechanism ${r.mechanism_id} has an S-curve profile and no jerk`;
    case "parallel_group_split":
      return `parallel group ${r.parallel_group} is split: another step sits between its members`;
    case "mechanism_overlap":
      return `mechanism ${r.mechanism_id} moves more than once in parallel group ${r.parallel_group}`;
  }
}

/** "not computable: a, b" or null when the station has a cycle time. */
export function notComputableText(reasons: NotComputableReason[]): string | null {
  return reasons.length === 0 ? null : `not computable: ${reasons.map(reasonText).join("; ")}`;
}

// The model's unit of each bounds field (mirrors MECHANISM_UNITS and TRANSPORT_UNITS in
// backend/app/engines/bounds.py).
const MECHANISM_UNITS: Record<string, { linear: string; rotary: string }> = {
  stroke: { linear: "mm", rotary: "deg" },
  max_speed: { linear: "mm/s", rotary: "deg/s" },
  acceleration: { linear: "mm/s²", rotary: "deg/s²" },
  jerk: { linear: "mm/s³", rotary: "deg/s³" },
};
const TRANSPORT_UNITS: Record<string, string> = { index_time_s: "s", speed_mm_s: "mm/s" };

function unitOf(w: TimingWarning, design?: MachineDesign): string {
  if (!w.field) return "";
  if (w.transport_id) return ` ${TRANSPORT_UNITS[w.field] ?? ""}`;
  const kind = design?.stations
    .find((s) => s.id === w.station_id)
    ?.mechanisms.find((m) => m.id === w.mechanism_id)?.kind;
  return kind && MECHANISM_UNITS[w.field] ? ` ${MECHANISM_UNITS[w.field][kind]}` : "";
}

/** The warning as a sentence. The design, when given, supplies the unit of a mechanism field. */
export function warningText(w: TimingWarning, design?: MachineDesign): string {
  if (w.code === "target_not_met") {
    return `cycle ${seconds(w.value)} is over the target ${seconds(w.limit)}; limiting step ${w.step_id}`;
  }
  const unit = unitOf(w, design);
  const what = `${w.mechanism_id ?? w.transport_id} ${w.field?.replace(/_/g, " ")}`;
  const side = w.bound === "min" ? "below the catalog minimum" : "above the catalog maximum";
  return `${what} ${w.value}${unit} is ${side} ${w.limit}${unit} (row ${w.row_id})`;
}

export const WARNING_LABEL: Record<TimingWarning["code"], string> = {
  target_not_met: "target not met",
  out_of_bounds: "out of bounds",
};
