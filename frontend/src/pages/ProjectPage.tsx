import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import Chat from "../components/Chat";
import DesignView from "../components/DesignView";
import DocumentsView from "../components/DocumentsView";
import LayoutView from "../components/LayoutView";
import RevisionsView from "../components/RevisionsView";
import SparePartsView from "../components/SparePartsView";
import type { MachineDesign, Project } from "../types";

const TABS = ["design", "layout", "parts", "docs", "revisions"] as const;
type Tab = (typeof TABS)[number];

export default function ProjectPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The open tab lives in the URL (?tab=layout) so a refresh or a shared link keeps it.
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.find((t) => t === params.get("tab")) ?? "design";
  const setTab = (t: Tab) => setParams(t === "design" ? {} : { tab: t }, { replace: true });
  // Which revision the right panel shows; null = latest.
  const [viewing, setViewing] = useState<{ number: number; design: MachineDesign } | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    api.project(id).then(setProject).catch((e: Error) => setError(e.message));
  }, [id]);

  const onUpdated = useCallback((p: Project) => {
    setProject(p);
    setViewing(null);
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!project) return <p className="text-slate-500">Loading…</p>;

  const revision = viewing?.number ?? project.latest_revision;
  const design = viewing?.design ?? project.design;
  const tabs: [Tab, string][] = [
    ["design", "Design"],
    ["layout", "3D layout"],
    ["parts", "Spare parts & suppliers"],
    ["docs", "Documents"],
    ["revisions", `Revisions (${project.latest_revision})`],
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr] print:block">
      <Chat project={project} onUpdated={onUpdated} draft={draft} setDraft={setDraft} />

      <section className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-slate-200 print:hidden dark:border-slate-800">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${
                tab === key ? "border-amber-500 font-medium" : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
          {viewing && (
            <span className="ml-auto rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
              Viewing revision {viewing.number} ·{" "}
              <button className="underline" onClick={() => setViewing(null)}>
                back to latest
              </button>
            </span>
          )}
        </div>

        {tab === "design" && <DesignView design={design} onAsk={(q) => setDraft(q)} />}
        {tab === "layout" && <LayoutView projectId={project.id} revision={revision} design={design} />}
        {tab === "parts" && <SparePartsView projectId={project.id} revision={revision} />}
        {tab === "docs" && <DocumentsView projectId={project.id} revision={revision} />}
        {tab === "revisions" && (
          <RevisionsView
            project={project}
            onView={(number, d) => {
              setViewing(number === project.latest_revision ? null : { number, design: d });
              setTab("design");
            }}
            onRestored={onUpdated}
          />
        )}
      </section>
    </div>
  );
}
