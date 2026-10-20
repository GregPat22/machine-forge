import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocSection, TechnicalDocument } from "../types";

const COLLAPSED_ROWS = 12;

function Section({ section }: { section: DocSection }) {
  const [expanded, setExpanded] = useState(false);
  const rows = section.table?.rows ?? [];
  const collapsible = rows.length > COLLAPSED_ROWS;

  return (
    <section className="break-inside-avoid-page">
      <h2 className="mb-2 text-lg font-semibold">{section.title}</h2>
      {section.paragraphs.map((p) => (
        <p key={p} className="mb-2 text-sm text-slate-700 dark:text-slate-300">
          {p}
        </p>
      ))}
      {section.bullets.length > 0 && (
        <ul className="mb-2 list-disc space-y-0.5 pl-5 text-sm text-slate-700 dark:text-slate-300">
          {section.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      {section.table && rows.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-200 dark:border-slate-800">
          <table className="w-full">
            <thead className="bg-slate-50 dark:bg-slate-800/50">
              <tr>
                {section.table.columns.map((c) => (
                  <th key={c} className="th">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {rows.map((row, i) => (
                <tr key={i} className={collapsible && !expanded && i >= COLLAPSED_ROWS ? "hidden print:table-row" : ""}>
                  {row.map((cell, j) => (
                    <td key={j} className={`td ${j === 0 && section.id === "io" ? "font-mono text-xs" : ""}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {collapsible && (
            <button
              className="w-full border-t border-slate-200 py-1.5 text-xs text-slate-500 hover:text-amber-600 print:hidden dark:border-slate-800"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Show less" : `Show all ${rows.length} rows`}
            </button>
          )}
        </div>
      )}
      {section.note && <p className="mt-1.5 text-xs text-slate-500 italic">{section.note}</p>}
    </section>
  );
}

export default function DocumentsView({ projectId, revision }: { projectId: string; revision: number }) {
  const [doc, setDoc] = useState<TechnicalDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDoc(null);
    api.documents(projectId, revision).then(setDoc).catch((e: Error) => setError(e.message));
  }, [projectId, revision]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!doc) return <p className="text-sm text-slate-500">Generating documents…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{doc.title}</h1>
          <p className="text-sm text-slate-500">{doc.subtitle}</p>
        </div>
        <div className="flex gap-2 print:hidden">
          <a className="btn-primary" href={api.documentUrl(projectId, revision, "docx")}>
            Word (.docx)
          </a>
          <a className="btn-secondary" href={api.documentUrl(projectId, revision, "md")}>
            Markdown
          </a>
          <button className="btn-secondary" onClick={() => window.print()}>
            Print / PDF
          </button>
        </div>
      </div>

      <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
        {doc.disclaimer}
      </div>

      <div className="flex flex-wrap gap-2">
        {Object.entries(doc.io_summary).map(([kind, n]) => (
          <span key={kind} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs dark:bg-slate-800">
            {kind}: <strong>{n}</strong>
          </span>
        ))}
      </div>

      {doc.sections.map((s) => (
        <Section key={s.id} section={s} />
      ))}
    </div>
  );
}
