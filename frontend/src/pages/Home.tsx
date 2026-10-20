import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, progressText } from "../api";
import type { Progress, ProjectSummary } from "../types";

const EXAMPLES = [
  "Pack 300 tablets per minute into PVC/Alu blisters of 10, for a pharmaceutical customer (GMP).",
  "Fill 120 vials per minute with a liquid nutraceutical, 10 ml ±1%, then cap and label them.",
  "Load 60 cosmetic tubes per minute with a leaflet into folding cartons and close them with hot melt.",
  "Assemble a valve body, spring and cap: 1200 pcs/h, with press force monitoring and 100% inspection.",
];

export default function Home() {
  const [problem, setProblem] = useState("");
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.projects().then(setProjects).catch((e: Error) => setError(e.message));
  }, []);

  async function create() {
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      const project = await api.createProject(problem, setProgress);
      navigate(`/projects/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this machine and all its revisions?")) return;
    await api.deleteProject(id);
    setProjects((ps) => ps.filter((p) => p.id !== id));
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[3fr_2fr]">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">What problem should the machine solve?</h1>
        <p className="mt-1 text-sm text-slate-500">
          Describe the product, the throughput and any constraints. You get a first machine design, then refine it by
          prompting. The spare-parts catalog and the supplier comparison follow every revision.
        </p>
        <textarea
          className="input mt-4 min-h-36"
          placeholder="e.g. We need to pack 300 tablets per minute into blisters…"
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              className="rounded-full border border-slate-300 px-3 py-1 text-left text-xs text-slate-600 hover:border-amber-500 dark:border-slate-700 dark:text-slate-300"
              onClick={() => setProblem(example)}
            >
              {example.length > 60 ? `${example.slice(0, 60)}…` : example}
            </button>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button className="btn-primary" disabled={busy || problem.trim().length < 10} onClick={create}>
            {busy ? "Designing the machine…" : "Design the machine"}
          </button>
          {busy && <span className="text-xs text-slate-500 italic">{progressText(progress)}</span>}
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-slate-500 uppercase">Your machines</h2>
        {projects.length === 0 && <p className="text-sm text-slate-500">No machines yet.</p>}
        <ul className="space-y-3">
          {projects.map((p) => (
            <li key={p.id} className="card flex items-start gap-3 p-4">
              <Link to={`/projects/${p.id}`} className="min-w-0 flex-1">
                <div className="font-medium hover:text-amber-600">{p.name}</div>
                <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{p.problem}</div>
                <div className="mt-1 text-xs text-slate-400">
                  Revision {p.latest_revision} · {new Date(p.updated_at).toLocaleString()}
                </div>
              </Link>
              <button className="text-xs text-slate-400 hover:text-red-600" onClick={() => remove(p.id)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
