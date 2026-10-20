import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import Home from "./pages/Home";
import ProjectPage from "./pages/ProjectPage";
import Suppliers from "./pages/Suppliers";
import type { AppStatus } from "./types";

function StatusPill({ status }: { status: AppStatus | null }) {
  if (!status) return null;
  const { llm } = status;
  const label = llm.ready ? `AI: ${llm.provider}${llm.model ? ` · ${llm.model}` : ""}` : "AI not configured";
  return (
    <span
      title={llm.error ?? undefined}
      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
        llm.ready
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
          : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
      }`}
    >
      {label}
    </span>
  );
}

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:text-white"}`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="bg-slate-900 text-white print:hidden">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
          <NavLink to="/" className="text-lg font-semibold tracking-tight">
            <span className="text-amber-400">⚙</span> Machine Forge
          </NavLink>
          <nav className="flex gap-1">
            <NavLink to="/" end className={link}>
              Machines
            </NavLink>
            <NavLink to="/suppliers" className={link}>
              Suppliers
            </NavLink>
          </nav>
          <div className="ml-auto">
            <StatusPill status={status} />
          </div>
        </div>
      </header>
      {status && !status.llm.ready && (
        <div className="bg-red-50 px-4 py-2 text-center text-sm text-red-800 print:hidden dark:bg-red-950 dark:text-red-200">
          {status.llm.error} See README → “Configure the AI”.
        </div>
      )}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/suppliers" element={<Suppliers />} />
        </Routes>
      </main>
    </div>
  );
}
