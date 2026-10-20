import { useEffect, useState } from "react";
import { api } from "../api";
import type { MachineDesign, Project, Revision } from "../types";

interface Props {
  project: Project;
  onView: (number: number, design: MachineDesign) => void;
  onRestored: (project: Project) => void;
}

export default function RevisionsView({ project, onView, onRestored }: Props) {
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.revisions(project.id).then(setRevisions).catch((e: Error) => setError(e.message));
  }, [project.id, project.latest_revision]);

  async function restore(n: number) {
    try {
      onRestored(await api.restore(project.id, n));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {[...revisions].reverse().map((r) => {
        const parts = r.design.stations.reduce((n, s) => n + s.components.length, 0);
        return (
          <div key={r.number} className="card flex items-start gap-4 p-4">
            <div className="w-10 shrink-0 font-mono text-sm text-slate-400">r{r.number}</div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">{r.prompt}</div>
              <div className="mt-0.5 text-sm text-slate-500">{r.reply}</div>
              <div className="mt-1 text-xs text-slate-400">
                {r.design.stations.length} stations · {parts} component lines · {new Date(r.created_at).toLocaleString()}
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
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
        );
      })}
    </div>
  );
}
