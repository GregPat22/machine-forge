import type {
  AppStatus,
  ConnectorStatus,
  PriceListEntry,
  Project,
  ProjectSummary,
  Revision,
  SourcingReport,
  SparePart,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // not JSON: keep the status text
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  status: () => request<AppStatus>("/status"),
  projects: () => request<ProjectSummary[]>("/projects"),
  createProject: (problem: string) => request<Project>("/projects", json({ problem })),
  project: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),
  prompt: (id: string, message: string) => request<Project>(`/projects/${id}/prompt`, json({ message })),
  revisions: (id: string) => request<Revision[]>(`/projects/${id}/revisions`),
  restore: (id: string, n: number) => request<Project>(`/projects/${id}/revisions/${n}/restore`, { method: "POST" }),
  spareParts: (id: string, revision: number) =>
    request<SparePart[]>(`/projects/${id}/spare-parts?revision=${revision}`),
  sparePartsCsvUrl: (id: string, revision: number) => `/api/projects/${id}/spare-parts.csv?revision=${revision}`,
  sourcing: (id: string, revision: number, external: boolean) =>
    request<SourcingReport>(`/projects/${id}/sourcing?revision=${revision}&external=${external}`),
  priceList: () => request<PriceListEntry[]>("/price-list"),
  uploadPriceList: (file: File, append: boolean) => {
    const form = new FormData();
    form.append("file", file);
    form.append("append", String(append));
    return request<{ imported: number; total: number }>("/price-list", { method: "POST", body: form });
  },
  connectors: () => request<ConnectorStatus[]>("/connectors"),
};

export function money(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
}
