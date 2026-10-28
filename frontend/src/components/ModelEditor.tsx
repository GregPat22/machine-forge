import { createContext, Fragment, useContext, useState, type FormEvent, type ReactNode } from "react";
import { api, PatchRejected, RevisionConflict } from "../api";
import type {
  Component,
  MachineDesign,
  Mechanism,
  Parameter,
  PatchOp,
  Project,
  Signals,
  Station,
  StationIn,
  Step,
  Transport,
} from "../types";

// The structured model editor (Phase 1, section G). Every save sends patch operations to the same
// endpoint and validator the AI goes through (`POST /api/projects/{id}/patches`) and makes a new
// revision. Nothing is checked or computed here: bounds, ids and references are the validator's
// job, and its errors are shown next to the form that caused them. The editor only uses the
// existing operations (ADR 0024), so it cannot remove a mechanism or a station parameter.

// Option lists mirror the enums in backend/app/models.py.
const STATION_KINDS = ["process", "transport", "inspection", "control", "frame", "safety", "utility"] as const;
const TRANSPORT_KINDS = ["belt", "indexing", "rotary", "pick_place", "gravity"] as const;
const MECHANISM_KINDS = ["linear", "rotary"] as const;
const STEP_KINDS = ["fixed_duration", "motion"] as const;
const ROLES = ["actuator", "sensor", "drive", "controller", "tooling", "structure", "consumable"] as const;
// prettier-ignore
const CATEGORIES = [
  "servo_motor", "motor", "gearbox", "drive", "plc", "io_module", "hmi", "safety", "sensor", "vision",
  "pneumatic_actuator", "pneumatic_valve", "air_treatment", "vacuum", "linear_motion", "bearing", "transmission",
  "conveyor", "heating", "cooling", "pump", "dosing", "cutting", "sealing", "printing_marking", "electrical",
  "frame_structure", "guarding", "custom_part", "other",
] as const;
const SIGNALS = ["di", "do", "ai", "ao", "axes", "fieldbus"] as const;

// --- Shared state: one save at a time, nothing editable on an older revision -------------------

interface Editor {
  /** The latest revision, the one shown and edited. */
  revision: number;
  /** Sends patches made on revision `basedOn`; null when saved, otherwise the messages to show. */
  save: (patches: PatchOp[], basedOn: number) => Promise<string[] | null>;
  busy: boolean;
  readOnly: boolean;
}

const EditorContext = createContext<Editor>({ revision: 0, save: async () => null, busy: false, readOnly: true });

// --- Generic form ------------------------------------------------------------------------------

type Kind =
  "text" | "optional_text" | "number" | "integer" | "optional_integer" | "select" | "optional_select" | "checkbox";

interface Field<T> {
  /** The model field it edits; absent for a field built by hand, such as one signal count. */
  key?: string;
  label: string;
  kind: Kind;
  get: (item: T) => unknown;
  set: (item: T, value: unknown) => T;
  options?: readonly string[];
  hint?: string;
  /** The item's id: set when adding, fixed when editing. */
  identity?: boolean;
  wide?: boolean;
}

function field<T>(key: keyof T & string, label: string, kind: Kind, extra: Partial<Field<T>> = {}): Field<T> {
  return { key, label, kind, get: (item) => item[key], set: (item, value) => ({ ...item, [key]: value }), ...extra };
}

function toText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Turns what was typed into the JSON value; bounds are left to the backend validator. */
function parse(f: { label: string; kind: Kind }, raw: string): { value: unknown } | { error: string } {
  const text = raw.trim();
  switch (f.kind) {
    case "text":
    case "select":
      return { value: raw };
    case "optional_text":
    case "optional_select":
      return { value: text === "" ? null : raw };
    case "checkbox":
      return { value: raw === "true" };
    case "number": {
      if (text === "") return { value: null };
      const n = Number(text);
      return Number.isFinite(n) ? { value: n } : { error: `${f.label} must be a number` };
    }
    case "integer":
    case "optional_integer": {
      if (text === "") return f.kind === "integer" ? { error: `${f.label} is required` } : { value: null };
      const n = Number(text);
      return Number.isInteger(n) ? { value: n } : { error: `${f.label} must be a whole number` };
    }
  }
}

interface FormProps<T> {
  testId: string;
  initial: T;
  fields: Field<T>[];
  locked: boolean; // identity fields fixed (editing an existing item)
  toPatches: (item: T) => PatchOp[];
  /** A problem the patches cannot express, shown instead of saving. */
  check?: (item: T) => string | null;
  onClose: () => void;
}

function ItemForm<T>({ testId, initial, fields, locked, toPatches, check, onClose }: FormProps<T>) {
  const { revision, save, busy } = useContext(EditorContext);
  // The revision the form was opened on: if another save lands meanwhile, this one gets a 409
  // instead of writing the values read before it over the newer revision.
  const [basedOn] = useState(revision);
  const [values, setValues] = useState(() => fields.map((f) => toText(f.get(initial))));
  const [errors, setErrors] = useState<string[]>([]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    let item = initial;
    const problems: string[] = [];
    fields.forEach((f, i) => {
      if (locked && f.identity) return;
      const result = parse(f, values[i]);
      if ("error" in result) problems.push(result.error);
      else item = f.set(item, result.value);
    });
    const problem = check?.(item);
    if (problem) problems.push(problem);
    if (problems.length > 0) return setErrors(problems);
    if (locked && JSON.stringify(item) === JSON.stringify(initial)) return onClose(); // nothing changed
    const patches = toPatches(item);
    if (patches.length === 0) return onClose();
    const failed = await save(patches, basedOn);
    if (failed) setErrors(failed);
    else onClose();
  }

  const setValue = (i: number, value: string) => setValues((vs) => vs.map((v, j) => (j === i ? value : v)));

  return (
    <form data-testid={testId} onSubmit={submit} className="space-y-2 rounded-md bg-slate-50 p-3 dark:bg-slate-800/50">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {fields.map((f, i) => {
          const disabled = locked && !!f.identity;
          const label = `${f.label}${f.hint ? ` (${f.hint})` : ""}`;
          if (f.kind === "checkbox") {
            return (
              <label key={f.label} className="flex items-center gap-2 self-end pb-2 text-xs">
                <input
                  type="checkbox"
                  checked={values[i] === "true"}
                  onChange={(e) => setValue(i, String(e.target.checked))}
                />
                {label}
              </label>
            );
          }
          return (
            <label key={f.label} className={`block text-xs ${f.wide ? "col-span-full" : ""}`}>
              <span className="text-slate-500">{label}</span>
              {f.kind === "select" || f.kind === "optional_select" ? (
                <select
                  aria-label={label} // otherwise the option texts become part of its name
                  className="input mt-0.5"
                  value={values[i]}
                  disabled={disabled}
                  onChange={(e) => setValue(i, e.target.value)}
                >
                  {f.kind === "optional_select" && <option value="">—</option>}
                  {/* A stored value outside the list (e.g. a reference to a removed item) stays visible. */}
                  {values[i] !== "" && !f.options?.includes(values[i]) && (
                    <option value={values[i]}>{values[i]}</option>
                  )}
                  {f.options?.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input mt-0.5"
                  value={values[i]}
                  disabled={disabled}
                  inputMode={["number", "integer", "optional_integer"].includes(f.kind) ? "decimal" : undefined}
                  onChange={(e) => setValue(i, e.target.value)}
                />
              )}
            </label>
          );
        })}
      </div>
      {errors.length > 0 && (
        <ul className="space-y-0.5 text-xs text-red-600">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// --- Generic list of items with edit, remove and add ------------------------------------------

interface Column<T> {
  label: string;
  render: (item: T) => ReactNode;
}

interface TableProps<T> {
  noun: string;
  title: string;
  items: T[];
  keyOf: (item: T) => string;
  columns: Column<T>[];
  fields: Field<T>[];
  newItem: () => T;
  onAdd: (item: T) => PatchOp[];
  checkAdd?: (item: T) => string | null;
  onEdit: (before: T, after: T) => PatchOp[];
  onRemove?: (item: T) => PatchOp[];
  note?: string;
}

function ItemTable<T>({
  noun,
  title,
  items,
  keyOf,
  columns,
  fields,
  newItem,
  onAdd,
  checkAdd,
  onEdit,
  onRemove,
  note,
}: TableProps<T>) {
  const { revision, save, busy, readOnly } = useContext(EditorContext);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  async function remove(item: T) {
    if (!onRemove || !confirm(`Remove ${noun} '${keyOf(item)}'? This makes a new revision.`)) return;
    setErrors((await save(onRemove(item), revision)) ?? []);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
          {title} ({items.length})
        </h4>
        {!readOnly && !adding && (
          <button
            className="text-xs text-amber-700 hover:underline dark:text-amber-400"
            onClick={() => setAdding(true)}
          >
            Add {noun}
          </button>
        )}
      </div>
      {note && <p className="text-[11px] text-slate-400">{note}</p>}
      {adding && !readOnly && (
        <ItemForm
          testId={`form-add-${noun}`}
          initial={newItem()}
          fields={fields}
          locked={false}
          toPatches={onAdd}
          check={checkAdd}
          onClose={() => setAdding(false)}
        />
      )}
      {errors.length > 0 && (
        <ul className="text-xs text-red-600">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.label} className="th">
                    {c.label}
                  </th>
                ))}
                {!readOnly && (
                  <th className="th">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((item) => {
                const key = keyOf(item);
                return (
                  <Fragment key={key}>
                    <tr data-testid={`${noun}-${key}`}>
                      {columns.map((c) => (
                        <td key={c.label} className="td">
                          {c.render(item)}
                        </td>
                      ))}
                      {!readOnly && (
                        <td className="td text-right text-xs whitespace-nowrap">
                          <button
                            className="text-amber-700 hover:underline dark:text-amber-400"
                            aria-label={`Edit ${noun} ${key}`}
                            onClick={() => setEditing(key)}
                          >
                            Edit
                          </button>
                          {onRemove && (
                            <button
                              className="ml-3 text-slate-400 hover:text-red-600"
                              disabled={busy}
                              aria-label={`Remove ${noun} ${key}`}
                              onClick={() => remove(item)}
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                    {editing === key && !readOnly && (
                      <tr>
                        <td colSpan={columns.length + 1} className="td">
                          <ItemForm
                            testId={`form-edit-${noun}-${key}`}
                            initial={item}
                            fields={fields}
                            locked
                            toPatches={(after) => onEdit(item, after)}
                            onClose={() => setEditing(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- Fields of each part of the model ------------------------------------------------------------

const show = (value: unknown, unit = "") =>
  value === null || value === undefined || value === "" ? "—" : `${value}${unit}`;

const parameterFields: Field<Parameter>[] = [
  field("name", "Name", "text", { identity: true }),
  field("value", "Value", "number"),
  field("unit", "Unit", "optional_text"),
];

const mechanismFields: Field<Mechanism>[] = [
  field("id", "Id", "text", { identity: true }),
  field("kind", "Kind", "select", { options: MECHANISM_KINDS }),
  field("stroke", "Stroke", "number", { hint: "mm or deg" }),
  field("max_speed", "Max speed", "number", { hint: "mm/s or deg/s" }),
  field("acceleration", "Acceleration", "number", { hint: "mm/s² or deg/s²" }),
  field("dwell_s", "Dwell", "number", { hint: "s" }),
  field("cam_profile", "Cam profile id", "optional_text"),
];

const stepFields = (mechanisms: string[]): Field<Step>[] => [
  field("id", "Id", "text", { identity: true }),
  field("order", "Order", "integer"),
  field("kind", "Kind", "select", { options: STEP_KINDS }),
  field("mechanism_id", "Mechanism", "optional_select", { options: mechanisms, hint: "motion steps" }),
  field("duration_s", "Duration", "number", { hint: "s, fixed-duration steps only" }),
  field("parallel_group", "Parallel group", "optional_integer"),
];

const signalField = (key: keyof Signals): Field<Component> => ({
  label: key.toUpperCase(),
  kind: "optional_integer",
  hint: "signals",
  get: (c) => c.signals?.[key] ?? null,
  // Signals stay "not known" (null) until one count is typed; then empty counts are 0.
  set: (c, value) =>
    value === null && c.signals === null
      ? c
      : {
          ...c,
          signals: { ...(c.signals ?? { di: 0, do: 0, ai: 0, ao: 0, axes: 0, fieldbus: 0 }), [key]: value ?? 0 },
        },
});

const componentFields = (mechanisms: string[]): Field<Component>[] => [
  field("id", "Id", "text", { identity: true }),
  field("name", "Name", "text"),
  field("category", "Category", "select", { options: CATEGORIES }),
  field("quantity", "Quantity", "integer"),
  field("role", "Role", "optional_select", { options: ROLES }),
  field("motion", "Moves mechanism", "optional_select", { options: mechanisms }),
  field("manufacturer", "Manufacturer", "optional_text"),
  field("part_number", "Part number", "optional_text"),
  field("make_or_buy", "Make or buy", "select", { options: ["buy", "make"] }),
  field("criticality", "Criticality", "select", { options: ["A", "B", "C"] }),
  field("recommended_spares", "Recommended spares", "integer"),
  field("wear_part", "Wear part", "checkbox"),
  ...SIGNALS.map(signalField),
  field("notes", "Notes", "optional_text", { wide: true }),
];

const transportFields = (stations: string[]): Field<Transport>[] => [
  field("id", "Id", "text", { identity: true }),
  field("from_station", "From station", "select", { options: stations }),
  field("to_station", "To station", "select", { options: stations }),
  field("kind", "Kind", "select", { options: TRANSPORT_KINDS }),
  field("length_mm", "Length", "number", { hint: "mm" }),
  field("speed_mm_s", "Speed", "number", { hint: "mm/s" }),
  field("index_time_s", "Index time", "number", { hint: "s" }),
  field("buffer_capacity", "Buffer capacity", "optional_integer", { hint: "products" }),
  field("products_per_move", "Products per move", "optional_integer"),
  field("reject_to", "Reject to station", "optional_select", { options: stations }),
  field("reject_rate", "Reject rate", "number", { hint: "0 to 1" }),
];

// Station fields that set_param can set, with the operand each one takes.
type StationFields = Pick<
  StationIn,
  "id" | "name" | "kind" | "function" | "library_ref" | "length_mm" | "width_mm" | "height_mm" | "target_cycle_time_s"
>;

const stationFields: Field<StationFields>[] = [
  field("id", "Id", "text", { identity: true }),
  field("name", "Name", "text"),
  field("kind", "Kind", "select", { options: STATION_KINDS }),
  field("library_ref", "Library module", "optional_text", { hint: "empty = custom" }),
  field("length_mm", "Length", "number", { hint: "mm, along the flow" }),
  field("width_mm", "Width", "number", { hint: "mm" }),
  field("height_mm", "Height", "number", { hint: "mm" }),
  field("target_cycle_time_s", "Target cycle time", "number", { hint: "s" }),
  field("function", "Function", "text", { wide: true }),
];

const STATION_FIELD_NAMES = new Set(stationFields.map((f) => f.key));
const NUMERIC_STATION_FIELDS = new Set(["length_mm", "width_mm", "height_mm", "target_cycle_time_s"]);

function stationEdits(station: Station, after: StationFields): PatchOp[] {
  return stationFields
    .filter((f) => !f.identity && f.get(after) !== f.get(station))
    .map((f): PatchOp => {
      const name = f.key!;
      return NUMERIC_STATION_FIELDS.has(name)
        ? { op: "set_param", station_id: station.id, name, value: f.get(after) as number | null }
        : { op: "set_param", station_id: station.id, name, text: f.get(after) as string | null };
    });
}

// --- Stations ----------------------------------------------------------------------------------

function StationCard({ station }: { station: Station }) {
  const { revision, save, busy, readOnly } = useContext(EditorContext);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const mechanismIds = station.mechanisms.map((m) => m.id);
  const sid = station.id;

  async function removeStation() {
    if (!confirm(`Remove station '${sid}'? This makes a new revision.`)) return;
    setErrors((await save([{ op: "remove_station", station_id: sid }], revision)) ?? []);
  }

  return (
    <div className="card" data-testid={`station-${sid}`}>
      <button
        className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 text-left"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="font-medium">{station.name}</span>
        <span className="font-mono text-xs text-slate-400">{sid}</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {station.kind}
        </span>
        <span className="ml-auto text-xs text-slate-400">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="space-y-5 border-t border-slate-200 px-4 py-4 dark:border-slate-800">
          <div className="space-y-2">
            {editing && !readOnly ? (
              <ItemForm
                testId={`form-edit-station-${sid}`}
                initial={station}
                fields={stationFields}
                locked
                toPatches={(after) => stationEdits(station, after)}
                onClose={() => setEditing(false)}
              />
            ) : (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm md:grid-cols-4">
                <Item label="Function" wide>
                  {station.function}
                </Item>
                <Item label="Library module">{station.library_ref ?? "custom"}</Item>
                <Item label="Envelope (L × W × H, mm)">
                  {show(station.length_mm)} × {show(station.width_mm)} × {show(station.height_mm)}
                </Item>
                <Item label="Target cycle time">{show(station.target_cycle_time_s, " s")}</Item>
                <Item label="Sequence (derived from the transports)">
                  {station.sequence > 0 ? station.sequence : "not in the product flow"}
                </Item>
                <Item label="Cycle time (derived from fixed-duration steps)">
                  {station.cycle_time_s === null ? "not computable yet" : `${station.cycle_time_s} s`}
                </Item>
              </dl>
            )}
            {!readOnly && !editing && (
              <div className="flex gap-4 text-xs">
                <button className="text-amber-700 hover:underline dark:text-amber-400" onClick={() => setEditing(true)}>
                  Edit station
                </button>
                <button className="text-slate-400 hover:text-red-600" disabled={busy} onClick={removeStation}>
                  Remove station
                </button>
              </div>
            )}
            {errors.length > 0 && (
              <ul className="text-xs text-red-600">
                {errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>

          <ItemTable<Parameter>
            noun="parameter"
            title="Parameters"
            items={station.parameters}
            keyOf={(p) => p.name}
            columns={[
              { label: "Name", render: (p) => p.name },
              { label: "Value", render: (p) => show(p.value) },
              { label: "Unit", render: (p) => show(p.unit) },
            ]}
            fields={parameterFields}
            newItem={() => ({ name: "", value: null, unit: null })}
            onAdd={(p) => [{ op: "set_param", station_id: sid, name: p.name, value: p.value, unit: p.unit }]}
            // set_param with a station field's name sets that field, not a parameter.
            checkAdd={(p) =>
              STATION_FIELD_NAMES.has(p.name.trim()) ? `'${p.name}' is a station field: use Edit station instead` : null
            }
            onEdit={(_, p) => [{ op: "set_param", station_id: sid, name: p.name, value: p.value, unit: p.unit }]}
            note="Parameters cannot be removed from the editor; ask the AI in the chat."
          />

          <ItemTable<Mechanism>
            noun="mechanism"
            title="Mechanisms"
            items={station.mechanisms}
            keyOf={(m) => m.id}
            columns={[
              { label: "Id", render: (m) => <span className="font-mono text-xs">{m.id}</span> },
              { label: "Kind", render: (m) => m.kind },
              { label: "Stroke", render: (m) => show(m.stroke, m.kind === "linear" ? " mm" : " deg") },
              { label: "Max speed", render: (m) => show(m.max_speed, m.kind === "linear" ? " mm/s" : " deg/s") },
              {
                label: "Acceleration",
                render: (m) => show(m.acceleration, m.kind === "linear" ? " mm/s²" : " deg/s²"),
              },
              { label: "Dwell", render: (m) => show(m.dwell_s, " s") },
            ]}
            fields={mechanismFields}
            newItem={() => ({
              id: "",
              kind: "linear",
              stroke: null,
              max_speed: null,
              acceleration: null,
              cam_profile: null,
              dwell_s: null,
            })}
            onAdd={(m) => [{ op: "add_mechanism", station_id: sid, mechanism: m }]}
            onEdit={(_, m) => [{ op: "set_mechanism", station_id: sid, mechanism: m }]}
            note="Mechanisms cannot be removed from the editor; ask the AI in the chat."
          />

          <ItemTable<Step>
            noun="step"
            title="Steps"
            items={[...station.steps].sort((a, b) => a.order - b.order)}
            keyOf={(s) => s.id}
            columns={[
              { label: "Order", render: (s) => s.order },
              { label: "Id", render: (s) => <span className="font-mono text-xs">{s.id}</span> },
              { label: "Kind", render: (s) => s.kind },
              { label: "Mechanism", render: (s) => show(s.mechanism_id) },
              { label: "Duration", render: (s) => show(s.duration_s, " s") },
              { label: "Parallel group", render: (s) => show(s.parallel_group) },
            ]}
            fields={stepFields(mechanismIds)}
            newItem={() => ({
              id: "",
              order: Math.max(0, ...station.steps.map((s) => s.order)) + 1,
              kind: "fixed_duration",
              mechanism_id: null,
              duration_s: null,
              parallel_group: null,
            })}
            onAdd={(s) => [{ op: "add_step", station_id: sid, step: s }]}
            // There is no set_step: the old step goes and the new one comes, in one all-or-nothing request.
            onEdit={(before, after) => [
              { op: "remove_step", station_id: sid, step_id: before.id },
              { op: "add_step", station_id: sid, step: after },
            ]}
            onRemove={(s) => [{ op: "remove_step", station_id: sid, step_id: s.id }]}
            note="A motion step's duration is computed by the software (Phase 2): leave it empty."
          />

          <ItemTable<Component>
            noun="component"
            title="Components"
            items={station.components}
            keyOf={(c) => c.id}
            columns={[
              {
                label: "Component",
                render: (c) => (
                  <>
                    <div>{c.name}</div>
                    <div className="font-mono text-[11px] text-slate-400">{c.id}</div>
                  </>
                ),
              },
              { label: "Category", render: (c) => c.category },
              { label: "Qty", render: (c) => c.quantity },
              { label: "Role", render: (c) => show(c.role) },
              { label: "Moves", render: (c) => show(c.motion) },
              {
                label: "Signals",
                render: (c) =>
                  c.signals === null
                    ? "not known"
                    : SIGNALS.filter((k) => c.signals![k] > 0)
                        .map((k) => `${c.signals![k]} ${k.toUpperCase()}`)
                        .join(" · ") || "none",
              },
              {
                label: "Manufacturer / P/N",
                render: (c) => `${c.manufacturer ?? "—"}${c.part_number ? ` · ${c.part_number}` : ""}`,
              },
            ]}
            fields={componentFields(mechanismIds)}
            newItem={() => ({
              id: "",
              name: "",
              category: "other",
              quantity: 1,
              specs: [],
              manufacturer: null,
              part_number: null,
              make_or_buy: "buy",
              wear_part: false,
              criticality: "C",
              recommended_spares: 0,
              notes: null,
              role: null,
              signals: null,
              motion: null,
            })}
            onAdd={(c) => [{ op: "add_component", station_id: sid, component: c }]}
            onEdit={(before, after) => [{ op: "replace_component", component_id: before.id, component: after }]}
            onRemove={(c) => [{ op: "remove_component", component_id: c.id }]}
            note="Specs are kept as they are; the editor does not change them."
          />
        </div>
      )}
    </div>
  );
}

function Item({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={wide ? "col-span-full" : ""}>
      <dt className="text-[11px] text-slate-400">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function AddStation() {
  const { readOnly } = useContext(EditorContext);
  const [open, setOpen] = useState(false);
  if (readOnly) return null;
  if (!open)
    return (
      <button className="text-xs text-amber-700 hover:underline dark:text-amber-400" onClick={() => setOpen(true)}>
        Add station
      </button>
    );
  const blank: StationFields = {
    id: "",
    name: "",
    kind: "process",
    function: "",
    library_ref: null,
    length_mm: null,
    width_mm: null,
    height_mm: null,
    target_cycle_time_s: null,
  };
  return (
    <ItemForm
      testId="form-add-station"
      initial={blank}
      fields={stationFields}
      locked={false}
      // A new station is sent without the derived sequence and cycle_time_s (ADR 0012).
      toPatches={(s) => {
        const station: StationIn = { ...s, components: [], parameters: [], mechanisms: [], steps: [], placement: null };
        return [{ op: "add_station", station }];
      }}
      onClose={() => setOpen(false)}
    />
  );
}

// --- The editor ----------------------------------------------------------------------------------

interface Props {
  project: Project;
  design: MachineDesign;
  /** Viewing an older revision: shown, not editable. */
  readOnly: boolean;
  onUpdated: (project: Project) => void;
}

export default function ModelEditor({ project, design, readOnly, onUpdated }: Props) {
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const stationIds = design.stations.map((s) => s.id);

  async function save(patches: PatchOp[], basedOn: number): Promise<string[] | null> {
    setBusy(true);
    try {
      onUpdated(await api.applyPatches(project.id, basedOn, patches));
      setConflict(false);
      return null;
    } catch (e) {
      if (e instanceof PatchRejected) {
        // With several ops in one save (e.g. editing a step), name the op each error belongs to.
        return e.errors.map((err) =>
          err.index !== null && patches.length > 1 && patches[err.index]
            ? `${patches[err.index].op}: ${err.message}`
            : err.message,
        );
      }
      if (e instanceof RevisionConflict) {
        setConflict(true);
        return ["Not saved: the project has a newer revision. Reload it, then open this form again."];
      }
      return [(e as Error).message];
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    try {
      onUpdated(await api.project(project.id));
      setConflict(false);
      setReloadError(null);
    } catch (e) {
      setReloadError((e as Error).message);
    }
  }

  return (
    <EditorContext.Provider value={{ revision: project.latest_revision, save, busy, readOnly }}>
      <div className="space-y-6">
        <p className="text-sm text-slate-500">
          {readOnly
            ? "This is an older revision: it can be viewed, not edited. Go back to the latest revision to edit."
            : "Edits go through the same checks as the AI's edits. Each save makes a new revision, listed in the chat and in Revisions."}
        </p>
        {conflict && (
          <div className="rounded-md bg-amber-100 px-3 py-2 text-sm text-amber-900">
            This project has a newer revision than the one you were editing (another tab or a chat turn). Nothing was
            saved.{" "}
            <button className="underline" onClick={reload}>
              Reload the project
            </button>
            {reloadError && <span className="ml-2 text-red-600">{reloadError}</span>}
          </div>
        )}

        <section className="space-y-2">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-slate-500">Stations ({design.stations.length})</h2>
            <AddStation />
          </div>
          {design.stations.map((s) => (
            <StationCard key={s.id} station={s} />
          ))}
        </section>

        <section className="card space-y-2 p-4">
          <ItemTable<Transport>
            noun="transport"
            title="Transports (process graph)"
            items={design.transports}
            keyOf={(t) => t.id}
            columns={[
              { label: "Id", render: (t) => <span className="font-mono text-xs">{t.id}</span> },
              { label: "From → to", render: (t) => `${t.from_station} → ${t.to_station}` },
              { label: "Kind", render: (t) => t.kind },
              { label: "Length", render: (t) => show(t.length_mm, " mm") },
              { label: "Speed", render: (t) => show(t.speed_mm_s, " mm/s") },
              { label: "Index time", render: (t) => show(t.index_time_s, " s") },
              { label: "Buffer", render: (t) => show(t.buffer_capacity) },
              { label: "Per move", render: (t) => show(t.products_per_move) },
              { label: "Reject", render: (t) => (t.reject_to ? `${t.reject_to} (${show(t.reject_rate)})` : "—") },
            ]}
            fields={transportFields(stationIds)}
            newItem={() => ({
              id: "",
              from_station: stationIds[0] ?? "",
              to_station: stationIds[1] ?? stationIds[0] ?? "",
              kind: "belt",
              length_mm: null,
              speed_mm_s: null,
              index_time_s: null,
              buffer_capacity: null,
              products_per_move: null,
              reject_to: null,
              reject_rate: null,
            })}
            onAdd={(t) => [{ op: "connect", transport: t }]}
            // There is no set_transport: disconnect and connect again, in one all-or-nothing request.
            onEdit={(before, after) => [
              { op: "disconnect", transport_id: before.id },
              { op: "connect", transport: after },
            ]}
            onRemove={(t) => [{ op: "disconnect", transport_id: t.id }]}
            note="A station's sequence is derived from these transports. Remove a station's transports before removing the station."
          />
        </section>
      </div>
    </EditorContext.Provider>
  );
}
