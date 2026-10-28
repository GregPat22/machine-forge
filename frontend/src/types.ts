// Mirrors backend/app/models.py

export type Criticality = "A" | "B" | "C";

export interface Spec {
  name: string;
  value: string;
}

export interface Signals {
  di: number;
  do: number;
  ai: number;
  ao: number;
  axes: number;
  fieldbus: number;
}

export interface Product {
  name: string | null;
  description: string | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  mass_g: number | null;
  orientation: "unspecified" | "upright" | "lying" | "on_edge";
  lanes: number | null;
  pitch_mm: number | null;
}

export interface Transport {
  id: string;
  from_station: string;
  to_station: string;
  kind: "belt" | "indexing" | "rotary" | "pick_place" | "gravity";
  length_mm: number | null;
  speed_mm_s: number | null;
  index_time_s: number | null;
  buffer_capacity: number | null;
  products_per_move: number | null;
  reject_to: string | null;
  reject_rate: number | null;
}

export interface Parameter {
  name: string;
  value: number | null;
  unit: string | null;
}

export interface Mechanism {
  id: string;
  kind: "linear" | "rotary";
  stroke: number | null;
  max_speed: number | null;
  acceleration: number | null;
  cam_profile: string | null;
  dwell_s: number | null;
}

export interface Step {
  id: string;
  order: number;
  kind: "motion" | "fixed_duration";
  mechanism_id: string | null;
  duration_s: number | null;
  parallel_group: number | null;
}

export interface Placement {
  x_mm: number;
  y_mm: number;
  rotation_deg: number;
}

export interface Component {
  id: string;
  name: string;
  category: string;
  quantity: number;
  specs: Spec[];
  manufacturer: string | null;
  part_number: string | null;
  make_or_buy: "buy" | "make";
  wear_part: boolean;
  criticality: Criticality;
  recommended_spares: number;
  notes: string | null;
  role: "actuator" | "sensor" | "drive" | "controller" | "tooling" | "structure" | "consumable" | null;
  signals: Signals | null;
  motion: string | null;
}

export interface Station {
  id: string;
  name: string;
  kind: "process" | "transport" | "inspection" | "control" | "frame" | "safety" | "utility";
  sequence: number;
  function: string;
  cycle_time_s: number | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  components: Component[];
  library_ref: string | null;
  parameters: Parameter[];
  mechanisms: Mechanism[];
  steps: Step[];
  target_cycle_time_s: number | null;
  placement: Placement | null;
}

/** A station as a patch sends it: `sequence` and `cycle_time_s` are derived and read-only (ADR 0012). */
export type StationIn = Omit<Station, "sequence" | "cycle_time_s">;

// Mirrors backend/app/services/patch.py: one flat edit, `op` plus the operands it uses (ADR 0013).
export type PatchOpKind =
  | "add_station"
  | "remove_station"
  | "set_param"
  | "add_component"
  | "remove_component"
  | "replace_component"
  | "add_mechanism"
  | "set_mechanism"
  | "add_step"
  | "remove_step"
  | "connect"
  | "disconnect"
  | "set_product"
  | "set_utility"
  | "add_assumption"
  | "add_open_question";

export interface PatchOp {
  op: PatchOpKind;
  station_id?: string | null;
  component_id?: string | null;
  step_id?: string | null;
  transport_id?: string | null;
  name?: string | null;
  value?: number | null;
  text?: string | null;
  unit?: string | null;
  items?: string[] | null;
  station?: StationIn | null;
  component?: Component | null;
  mechanism?: Mechanism | null;
  step?: Step | null;
  transport?: Transport | null;
  product?: Product | null;
}

export interface PatchError {
  /** Position of the rejected op in the list sent; null for the request as a whole. */
  index: number | null;
  code:
    | "unknown_station"
    | "unknown_component"
    | "unknown_mechanism"
    | "unknown_step"
    | "unknown_transport"
    | "duplicate_id"
    | "missing_operand"
    | "invalid_value"
    | "computed_field"
    | "graph_cycle"
    | "orphan_transport"
    | "unknown_op";
  message: string;
}

export interface MachineDesign {
  name: string;
  machine_type: string;
  summary: string;
  product: Product;
  target_rate_text: string | null;
  footprint: string | null;
  layout_style: "inline" | "u_shape";
  stations: Station[];
  transports: Transport[];
  utilities: string[];
  assumptions: string[];
  open_questions: string[];
  schema_version: 2;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  revision: number | null;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  problem: string;
  latest_revision: number;
  created_at: string;
  updated_at: string;
}

export interface Project extends ProjectSummary {
  messages: ChatMessage[];
  design: MachineDesign;
}

export interface Revision {
  number: number;
  prompt: string;
  reply: string;
  design: MachineDesign;
  schema_version: number;
  created_at: string;
}

export interface SparePart {
  item: number;
  key: string;
  name: string;
  category: string;
  specs: Spec[];
  manufacturer: string | null;
  part_number: string | null;
  make_or_buy: "buy" | "make";
  quantity_in_machine: number;
  used_in: string[];
  component_ids: string[];
  wear_part: boolean;
  criticality: Criticality;
  recommended_spares: number;
}

export interface Offer {
  source: string;
  supplier: string;
  manufacturer: string | null;
  part_number: string | null;
  description: string | null;
  unit_price: number | null;
  currency: string | null;
  unit_price_base: number | null;
  moq: number | null;
  stock: number | null;
  lead_time_days: number | null;
  url: string | null;
  match: "exact" | "similar";
  is_current: boolean;
  rating: number | null;
  preferred: boolean;
  score: number | null;
}

export interface SourcingLine {
  part: SparePart;
  offers: Offer[];
  current: Offer | null;
  best: Offer | null;
  savings_base: number | null;
  note: string | null;
}

export interface SourcingReport {
  project_id: string;
  revision: number;
  base_currency: string;
  lines: SourcingLine[];
  connectors_used: string[];
  connector_errors: string[];
  total_current_base: number | null;
  total_best_base: number | null;
}

export interface PriceListEntry {
  id: number | null;
  supplier: string;
  manufacturer: string | null;
  part_number: string | null;
  description: string | null;
  unit_price: number | null;
  currency: string;
  lead_time_days: number | null;
  moq: number | null;
  source_file: string | null;
}

export interface ConnectorStatus {
  name: string;
  label: string;
  configured: boolean;
  covers: string;
  setup: string;
}

export interface AppStatus {
  llm: { provider: string; model: string | null; ready: boolean; error: string | null };
  base_currency: string;
}

export interface LayoutBox {
  id: string;
  station_id: string | null;
  label: string;
  kind: string;
  sequence: number | null;
  x: number;
  y: number;
  z: number;
  length: number;
  width: number;
  height: number;
}

export interface Layout {
  style: "inline" | "u_shape";
  boxes: LayoutBox[];
  flow: [number, number, number][];
  footprint_length_mm: number;
  footprint_width_mm: number;
}

export interface DocTable {
  columns: string[];
  rows: string[][];
}

export interface DocSection {
  id: string;
  title: string;
  paragraphs: string[];
  bullets: string[];
  table: DocTable | null;
  note: string | null;
}

export interface TechnicalDocument {
  title: string;
  subtitle: string;
  revision: number;
  generated_at: string;
  disclaimer: string;
  io_summary: Record<string, number>;
  sections: DocSection[];
}

export interface FieldChange {
  field: string;
  before: string | null;
  after: string | null;
}

export interface DesignDiff {
  from_revision: number;
  to_revision: number;
  machine: FieldChange[];
  lists: { field: string; added: string[]; removed: string[] }[];
  stations: { station_id: string; name: string; change: "added" | "removed" | "modified"; fields: FieldChange[] }[];
  components: {
    component_id: string;
    name: string;
    station: string;
    change: "added" | "removed" | "modified";
    fields: FieldChange[];
  }[];
  counts: Record<string, number>;
}

export interface PlcProject {
  name: string;
  files: { name: string; content: string }[];
  io_counts: Record<string, number>;
  axes: string[];
  warnings: string[];
}

export interface SupplierInfo {
  name: string;
  quality: number | null;
  delivery: number | null;
  preferred: boolean;
  notes: string | null;
  price_list_items: number;
}

export interface Progress {
  phase: "waiting" | "thinking" | "writing";
  chars: number;
  stations: number;
  components: number;
  note: string | null;
}

export interface TemplateStatus {
  exists: boolean;
  size?: number;
  uploaded_at?: string;
}
