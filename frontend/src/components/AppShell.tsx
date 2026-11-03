import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { api } from "../api";
import type { AppStatus } from "../types";
import Icon from "./Icon";

export default function AppShell({
  children,
  sidebar,
  title,
  revision,
  actions,
}: {
  children: ReactNode;
  sidebar?: ReactNode;
  title: string;
  revision?: number;
  actions?: ReactNode;
}) {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const menu = useRef<HTMLDialogElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    let obsolete = false;
    api
      .status()
      .then((value) => {
        if (!obsolete) setStatus(value);
      })
      .catch((e: Error) => {
        if (!obsolete) setStatusError(e.message);
      });
    return () => {
      obsolete = true;
    };
  }, []);
  const closeMenu = () => {
    menu.current?.close();
    setMenuOpen(false);
  };
  const navigation = (
    <>
      <Link className="brand" to="/" aria-label="Machine Forge home">
        <span className="brand-meta">
          MF / CONCEPT ENGINEERING <span>↗</span>
        </span>
        <span className="brand-logo">
          <img src="/brand/mf-eagle.png" alt="MF eagle monogram" />
        </span>
        <span className="brand-name">
          Machine
          <br />
          Forge<span>.</span>
        </span>
      </Link>
      {sidebar}
      <div className="sidebar-label">Workspace</div>
      <nav className="project-nav workspace-nav" aria-label="Workspace">
        <NavLink to="/" end>
          <Icon name="machine" />
          <span>Machines</span>
        </NavLink>
        <NavLink to="/suppliers">
          <Icon name="parts" />
          <span>Suppliers</span>
        </NavLink>
      </nav>
      <div className="sidebar-bottom" role="status">
        <span className={`provider-dot ${status?.llm.ready ? "ready" : ""}`} />
        <span>
          {status
            ? status.llm.ready
              ? status.llm.provider === "mock"
                ? "Offline demo"
                : `AI: ${status.llm.provider}`
              : "AI not configured"
            : statusError
              ? "AI status unavailable"
              : "Checking AI status…"}
        </span>
        <p>{status?.llm.error ?? statusError ?? "Concept engineering workspace"}</p>
      </div>
    </>
  );
  return (
    <div className="app-layout">
      <aside className="app-sidebar">{navigation}</aside>
      <dialog
        className="navigation-dialog"
        ref={menu}
        aria-label="Navigation"
        onClose={() => setMenuOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) closeMenu();
        }}
      >
        <div
          className="mobile-sidebar"
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("a, .project-nav button")) closeMenu();
          }}
        >
          <button className="sidebar-close icon-button" onClick={closeMenu} aria-label="Close navigation">
            <Icon name="close" />
          </button>
          {navigation}
        </div>
      </dialog>
      <div className="app-main">
        <header className="app-topbar">
          <button
            className="mobile-toggle icon-button"
            aria-label="Open navigation"
            aria-expanded={menuOpen}
            onClick={() => {
              menu.current?.showModal();
              setMenuOpen(true);
            }}
          >
            <Icon name="menu" />
          </button>
          <div className="breadcrumbs">
            <Link to="/">Machines</Link>
            <Icon name="chevron" size={13} />
            <span title={title}>{title}</span>
          </div>
          <div className="topbar-actions">
            {revision !== undefined && <span className="revision-chip">REV {String(revision).padStart(2, "0")}</span>}
            {actions}
          </div>
        </header>
        {status && !status.llm.ready && (
          <div className="configuration-message">
            {status.llm.error ?? "Configure an AI provider to create or refine a machine."} See README → Configure the
            AI.
          </div>
        )}
        <main className="page-content" id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
