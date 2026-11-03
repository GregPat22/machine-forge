import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import AppShell from "../components/AppShell";
import ProjectSidebar, { PROJECT_TABS, type ProjectTab } from "../components/ProjectSidebar";
import Icon from "../components/Icon";
import Chat from "../components/Chat";
import DesignView from "../components/DesignView";
import DocumentsView from "../components/DocumentsView";
import LayoutView from "../components/LayoutView";
import ModelEditor from "../components/ModelEditor";
import PlcView from "../components/PlcView";
import RevisionsView from "../components/RevisionsView";
import SparePartsView from "../components/SparePartsView";
import TimingView from "../components/TimingView";
import type { MachineDesign, Project } from "../types";

export default function ProjectPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const tab: ProjectTab = PROJECT_TABS.find((t) => t === params.get("tab")) ?? "design";
  const [viewing, setViewing] = useState<{ number: number; design: MachineDesign } | null>(null);
  const [draft, setDraft] = useState("");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const assistant = useRef<HTMLDialogElement>(null);
  const setTab = (next: ProjectTab, stationId?: string) => {
    const nextParams = new URLSearchParams();
    if (next !== "design") nextParams.set("tab", next);
    if (next === "model" && stationId) nextParams.set("station", stationId);
    setParams(nextParams, { replace: true });
  };
  useEffect(() => {
    let obsolete = false;
    setError(null);
    setViewing(null);
    setDraft("");
    setAssistantOpen(false);
    api
      .project(id)
      .then((value) => {
        if (!obsolete) setProject(value);
      })
      .catch((e: Error) => {
        if (!obsolete) setError(e.message);
      });
    return () => {
      obsolete = true;
    };
  }, [id]);
  const onUpdated = useCallback((value: Project) => {
    setProject(value);
    setViewing(null);
  }, []);
  useEffect(() => {
    if (assistantOpen && !assistant.current?.open) assistant.current?.showModal();
    else if (!assistantOpen) assistant.current?.close();
  }, [assistantOpen]);
  const current = project?.id === id ? project : null;
  const design = viewing?.design ?? current?.design;
  const focusStation = params.get("station");
  useEffect(() => {
    if (design && focusStation && !design.stations.some((s) => s.id === focusStation)) {
      const next = new URLSearchParams(params);
      next.delete("station");
      setParams(next, { replace: true });
    }
  }, [design, focusStation, params, setParams]);
  if (!current || !design)
    return (
      <AppShell title="Machine project">
        <p className={error ? "text-red-700" : "muted"} role={error ? "alert" : "status"}>
          {error ?? "Loading the machine…"}
        </p>
      </AppShell>
    );
  const revision = viewing?.number ?? current.latest_revision;
  const openAssistant = (question?: string) => {
    if (question !== undefined) setDraft(`${question} → `);
    setAssistantOpen(true);
  };
  const headings: Partial<Record<ProjectTab, [string, string]>> = {
    timing: ["Station timing", "Check computed cycles, critical paths and unresolved timing inputs."],
    model: ["Machine model", "Inspect and edit the engineering inputs. Each save creates a checked revision."],
    layout: ["Layout & drawings", "Inspect the concept layout and download its top view."],
    parts: ["Parts & suppliers", "Review the parts in this revision and compare available offers."],
    revisions: ["Revision history", "Inspect, compare and restore the machine's revisions."],
  };
  return (
    <AppShell
      title={current.name}
      revision={revision}
      actions={
        <button className="btn-secondary" aria-label="Engineering assistant" onClick={() => openAssistant()}>
          <Icon name="spark" size={17} />
          <span>Assistant</span>
        </button>
      }
      sidebar={
        <ProjectSidebar name={current.name} revisionCount={current.latest_revision} tab={tab} onNavigate={setTab} />
      }
    >
      {viewing && (
        <div className="historical-banner" data-testid="historical-revision">
          <span>
            Viewing revision {viewing.number} · read-only. Latest is revision {current.latest_revision}.
          </span>
          <button onClick={() => setViewing(null)}>Back to latest</button>
        </div>
      )}
      {headings[tab] && (
        <section className="project-heading">
          <div>
            <p className="eyebrow">Machine workspace</p>
            <h1>{headings[tab]![0]}</h1>
            <p>{headings[tab]![1]}</p>
          </div>
        </section>
      )}
      <section className="work-area">
        {tab === "design" && (
          <DesignView
            key={`${id}:${revision}`}
            projectId={id}
            revision={revision}
            design={design}
            readOnly={viewing !== null}
            onAsk={openAssistant}
            onModel={(stationId) => setTab("model", stationId)}
          />
        )}
        {tab === "model" && (
          <ModelEditor
            project={current}
            design={design}
            revision={revision}
            readOnly={viewing !== null}
            onUpdated={onUpdated}
            focusStationId={focusStation}
          />
        )}
        {tab === "timing" && <TimingView projectId={id} revision={revision} design={design} />}
        {tab === "layout" && (
          <LayoutView key={`${id}:${revision}`} projectId={id} revision={revision} design={design} />
        )}
        {tab === "parts" && <SparePartsView key={`${id}:${revision}`} projectId={id} revision={revision} />}
        {tab === "docs" && <DocumentsView key={`${id}:${revision}`} projectId={id} revision={revision} />}
        {tab === "plc" && <PlcView key={`${id}:${revision}`} projectId={id} revision={revision} />}
        {tab === "revisions" && (
          <RevisionsView
            project={current}
            onView={(number, value) => {
              setViewing(number === current.latest_revision ? null : { number, design: value });
              setTab("design");
            }}
            onRestored={onUpdated}
          />
        )}
      </section>
      <dialog
        className="assistant-dialog"
        ref={assistant}
        aria-labelledby="assistant-title"
        onClose={() => setAssistantOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) assistant.current?.close();
        }}
      >
        <header className="dialog-heading">
          <div>
            <p className="eyebrow">Refine the machine</p>
            <h2 id="assistant-title">Engineering assistant</h2>
          </div>
          <button className="icon-button" aria-label="Close assistant" onClick={() => assistant.current?.close()}>
            <Icon name="close" />
          </button>
        </header>
        <Chat
          key={id}
          project={current}
          onUpdated={onUpdated}
          draft={draft}
          setDraft={setDraft}
          viewingHistory={viewing !== null}
          visible={assistantOpen}
        />
      </dialog>
    </AppShell>
  );
}
