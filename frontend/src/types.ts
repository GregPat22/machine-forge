// Mirrors backend/app/models.py

export type Criticality = "A" | "B" | "C";

export interface Spec {
  name: string;
  value: string;
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
}

export interface Station {
  id: string;
  name: string;
  kind: "process" | "transport" | "inspection" | "control" | "frame" | "safety" | "utility";
  sequence: number;
  function: string;
  cycle_time_s: number | null;
  components: Component[];
}

export interface MachineDesign {
  name: string;
  machine_type: string;
  summary: string;
  product: string;
  throughput: string | null;
  footprint: string | null;
  stations: Station[];
  utilities: string[];
  assumptions: string[];
  open_questions: string[];
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
