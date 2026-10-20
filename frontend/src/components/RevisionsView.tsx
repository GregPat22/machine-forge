import { useEffect, useState } from "react";
import { api } from "../api";
import DiffView from "./DiffView";
import type { MachineDesign, Project, Revision } from "../types";

interface Props {
  project: Project;
  onView: (number: number, design: MachineDesign) => void;
  onRestored: (project: Project) => void;
}

export default function RevisionsView({ project, onView, onRestored }: Props) {
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Revision whose changes (vs. the previous one) are expanded; the compare panel covers the latest.
  const [open, setOpen] = useState<number | null>(null);
  const [compare, setCompare] = useState<{ from: number; to: number }>({
    from: Math.max(project.latest_revision - 1, 1),
    to: project.latest_revision,
  });

  useEffect(() => {
    api.revisions(project.id).then(setRevisions).catch((e: Error) => setError(e.message));
    // A new revision arrived: compare it with the one before.
    setCompare({ from: Math.max(project.latest_revision - 1, 1), to: project.latest_revision });
  }, [project.id, project.latest_revision]);

  async function restore(n: number) {
    try {
      onRestored(await api.restore(project.id, n));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const numbers = revisions.map((r) => r.number);

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600">{error}</p>}

      {numbers.length > 1 && (
        <div className="card p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Compare</span>
            {(["from", "to"] as const).map((key) => (
              <select
                key={key}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
                value={compare[key]}
                onChange={(e) => setCompare({ ...compare, [key]: Number(e.target.value) })}
              >
                {numbers.map((n) => (
                  <option key={n} value={n}>
                    r{n}
                  </option>
                ))}
              </select>
            ))}
          </div>
          <DiffView projectId={project.id} from={compare.from} to={compare.to} />
        </div>
      )}

      <div className="space-y-2">
        {[...revisions].reverse().map((r) => {
          const parts = r.design.stations.reduce((n, s) => n + s.components.length, 0);
          return (
            <div key={r.number} className="card p-4">
              <div className="flex items-start gap-4">
                <div className="w-10 shrink-0 font-mono text-sm text-slate-400">r{r.number}</div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{r.prompt}</div>
                  <div className="mt-0.5 text-sm text-slate-500">{r.reply}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    {r.design.stations.length} stations · {parts} component lines ·{" "}
                    {new Date(r.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  {r.number > 1 && (
                    <button className="btn-secondary" onClick={() => setOpen(open === r.number ? null : r.number)}>
                      {open === r.number ? "Hide changes" : "Changes"}
                    </button>
                  )}
                  <button className="btn-secondary" onClick={() => onView(r.number, r.design)}>
                    View
                  </button>
                  {r.number !== project.latest_revision && (
                    <button className="btn-secondary" onClick={() => restore(r.number)}>
                      Restore
                    </button>
                  )}
                </div>
              </div>
              {open === r.number && (
                <div className="mt-3 ml-14 border-t border-slate-100 pt-3 dark:border-slate-800">
                  <DiffView projectId={project.id} from={r.number - 1} to={r.number} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
