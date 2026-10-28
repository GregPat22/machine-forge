import type {
  AppStatus,
  ConnectorStatus,
  DesignDiff,
  Layout,
  PlcProject,
  PriceListEntry,
  Progress,
  Project,
  ProjectSummary,
  Revision,
  SourcingReport,
  SparePart,
  SupplierInfo,
  TechnicalDocument,
  TemplateStatus,
} from "./types";

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (body.detail) return JSON.stringify(body.detail);
  } catch {
    // not JSON: fall back to the status text
  }
  return `${response.status} ${response.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) throw new Error(await errorDetail(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** POST to a server-sent-events endpoint: reports `progress` events, resolves with the `done` payload. */
async function streamDesign(path: string, body: unknown, onProgress: (p: Progress) => void): Promise<Project> {
  const response = await fetch(`/api${path}`, json(body));
  if (!response.ok || !response.body) throw new Error(await errorDetail(response));
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue; // keep-alive comment
      const payload = JSON.parse(data);
      if (event === "progress") onProgress(payload as Progress);
      else if (event === "done") return payload as Project;
      else if (event === "error") throw new Error(payload.detail ?? "Design failed");
    }
  }
  throw new Error("The connection closed before the design was finished.");
}

const rev = (revision: number) => `revision=${revision}`;

export const api = {
  status: () => request<AppStatus>("/status"),
  projects: () => request<ProjectSummary[]>("/projects"),
  createProject: (problem: string, onProgress: (p: Progress) => void) =>
    streamDesign("/projects/stream", { problem }, onProgress),
  project: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),
  prompt: (id: string, message: string, onProgress: (p: Progress) => void) =>
    streamDesign(`/projects/${id}/prompt/stream`, { message }, onProgress),
  revisions: (id: string) => request<Revision[]>(`/projects/${id}/revisions`),
  restore: (id: string, n: number) => request<Project>(`/projects/${id}/revisions/${n}/restore`, { method: "POST" }),
  diff: (id: string, from: number, to: number) => request<DesignDiff>(`/projects/${id}/diff?from=${from}&to=${to}`),
  spareParts: (id: string, revision: number) => request<SparePart[]>(`/projects/${id}/spare-parts?${rev(revision)}`),
  sparePartsCsvUrl: (id: string, revision: number) => `/api/projects/${id}/spare-parts.csv?${rev(revision)}`,
  rfqUrl: (id: string, revision: number) => `/api/projects/${id}/rfq.xlsx?${rev(revision)}`,
  layout: (id: string, revision: number) => request<Layout>(`/projects/${id}/layout?${rev(revision)}`),
  layoutFileUrl: (id: string, revision: number, format: "svg" | "dxf") =>
    `/api/projects/${id}/layout.${format}?${rev(revision)}`,
  documents: (id: string, revision: number) => request<TechnicalDocument>(`/projects/${id}/documents?${rev(revision)}`),
  documentUrl: (id: string, revision: number, format: "docx" | "md") =>
    `/api/projects/${id}/documents.${format}?${rev(revision)}`,
  plc: (id: string, revision: number) => request<PlcProject>(`/projects/${id}/plc?${rev(revision)}`),
  plcFileUrl: (id: string, revision: number, format: "zip" | "xml") => `/api/projects/${id}/plc.${format}?${rev(revision)}`,
  sourcing: (id: string, revision: number, external: boolean) =>
    request<SourcingReport>(`/projects/${id}/sourcing?${rev(revision)}&external=${external}`),
  priceList: () => request<PriceListEntry[]>("/price-list"),
  uploadPriceList: (file: File, append: boolean) => {
    const form = new FormData();
    form.append("file", file);
    form.append("append", String(append));
    return request<{ imported: number; total: number }>("/price-list", { method: "POST", body: form });
  },
  connectors: () => request<ConnectorStatus[]>("/connectors"),
  suppliers: () => request<SupplierInfo[]>("/suppliers"),
  rateSupplier: (name: string, rating: Pick<SupplierInfo, "quality" | "delivery" | "preferred" | "notes">) =>
    request<SupplierInfo>(`/suppliers/${encodeURIComponent(name)}`, json(rating, "PUT")),
  templateStatus: () => request<TemplateStatus>("/templates/document"),
  uploadTemplate: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<TemplateStatus>("/templates/document", { method: "POST", body: form });
  },
  deleteTemplate: () => request<void>("/templates/document", { method: "DELETE" }),
};

export function money(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  // Older imported rows may contain a currency that Intl.NumberFormat cannot accept.
  if (!/^[A-Za-z]{3}$/.test(currency)) {
    return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)} ${currency}`;
  }
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
}

export function progressText(p: Progress | null): string {
  if (!p) return "Starting…";
  if (p.phase === "waiting") return "Waiting for the model…";
  if (p.phase === "thinking") return p.note ? `Thinking: ${p.note}` : "Thinking…";
  return `Writing the design: ${p.stations} stations, ${p.components} components so far`;
}
