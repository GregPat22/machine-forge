import { useEffect, useRef, useState } from "react";
import { api, progressText } from "../api";
import type { Progress, Project } from "../types";

interface Props {
  project: Project;
  onUpdated: (project: Project) => void;
  draft: string;
  setDraft: (text: string) => void;
  viewingHistory?: boolean;
  visible: boolean;
}

const SUGGESTIONS = [
  "Add 100% vision inspection before the outfeed",
  "Increase throughput by 30%: what has to change?",
  "Replace the pneumatic actuators with servo axes where it makes sense",
  "Make it washdown-ready (IP69K) for food",
  "Make the line U-shaped, the hall is short",
];

export default function Chat({ project, onUpdated, draft, setDraft, viewingHistory, visible }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const list = useRef<HTMLDivElement>(null);

  // Scroll only the message list, never the page.
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [project.messages.length, busy, progress, visible]);

  async function send() {
    const message = draft.trim();
    if (!message) return;
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      onUpdated(await api.prompt(project.id, message, setProgress));
      setDraft("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="chat print:hidden">
      <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="truncate font-semibold">{project.name}</div>
        <div className="text-xs text-slate-500">{viewingHistory ? `Prompts edit the latest revision (${project.latest_revision}). Historical revisions remain read-only.` : "Refine the machine by prompting"}</div>
      </div>

      <div ref={list} className="chat-messages space-y-3">
        {project.messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex"}>
            <div
              className={`max-w-[90%] rounded-sm px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                m.role === "user" ? "bg-brand-100 text-slate-900" : "bg-slate-100"
              }`}
            >
              {m.content}
              {m.revision !== null && <div className="mt-1 text-[11px] text-slate-500">→ revision {m.revision}</div>}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-end">
            <div className="max-w-[90%] rounded-sm bg-brand-100 px-3 py-2 text-sm whitespace-pre-wrap">
              {draft}
            </div>
          </div>
        )}
        {busy && (
          <div className="flex items-start gap-2 text-sm text-slate-500">
            <span className="mt-1.5 h-2 w-2 shrink-0 animate-pulse rounded-full bg-brand-600" />
            <span className="italic">{progressText(progress)}</span>
          </div>
        )}
      </div>

      <div className="chat-composer">
        <details className="example-options"><summary>Ideas for your next change</summary><div className="chat-suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="text-left"
              onClick={() => setDraft(s)}
            >
              {s}
            </button>
          ))}
        </div></details>
        <textarea
          className="input min-h-20"
          aria-label="Message"
          placeholder="e.g. Use Beckhoff instead of Siemens for the control system"
          value={draft}
          disabled={busy}
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
