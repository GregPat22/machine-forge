import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Project } from "../types";

interface Props {
  project: Project;
  onUpdated: (project: Project) => void;
  draft: string;
  setDraft: (text: string) => void;
}

const SUGGESTIONS = [
  "Add 100% vision inspection before the outfeed",
  "Increase throughput by 30%: what has to change?",
  "Replace the pneumatic actuators with servo axes where it makes sense",
  "Make it washdown-ready (IP69K) for food",
];

export default function Chat({ project, onUpdated, draft, setDraft }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);

  // Scroll only the message list, never the page.
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [project.messages.length, busy]);

  async function send() {
    const message = draft.trim();
    if (!message) return;
    setBusy(true);
    setError(null);
    try {
      onUpdated(await api.prompt(project.id, message));
      setDraft("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="card flex h-[calc(100vh-8rem)] flex-col lg:sticky lg:top-4">
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="truncate font-semibold">{project.name}</div>
        <div className="text-xs text-slate-500">Refine the machine by prompting</div>
      </div>

      <div ref={list} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {project.messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex"}>
            <div
              className={`max-w-[90%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user" ? "bg-amber-100 text-slate-900 dark:bg-amber-900/40 dark:text-amber-50" : "bg-slate-100 dark:bg-slate-800"
              }`}
            >
              {m.content}
              {m.revision !== null && <div className="mt-1 text-[11px] text-slate-500">→ revision {m.revision}</div>}
            </div>
          </div>
        ))}
        {busy && <div className="text-sm text-slate-500 italic">Updating the design…</div>}
      </div>

      <div className="border-t border-slate-200 p-3 dark:border-slate-800">
        <div className="mb-2 flex flex-wrap gap-1">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="rounded-full border border-slate-300 px-2 py-0.5 text-[11px] text-slate-600 hover:border-amber-500 dark:border-slate-700 dark:text-slate-300"
              onClick={() => setDraft(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <textarea
          className="input min-h-20"
          placeholder="e.g. Use Beckhoff instead of Siemens for the control system"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">Ctrl+Enter to send</span>
          <button className="btn-primary" disabled={busy || !draft.trim()} onClick={send}>
            {busy ? "Working…" : "Send"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </div>
    </aside>
  );
}
