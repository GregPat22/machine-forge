import Icon, { type IconName } from "./Icon";

export const PROJECT_TABS = ["design", "model", "timing", "layout", "parts", "docs", "plc", "revisions"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];

export default function ProjectSidebar({
  name,
  revisionCount,
  tab,
  onNavigate,
}: {
  name: string;
  revisionCount: number;
  tab: ProjectTab;
  onNavigate: (tab: ProjectTab) => void;
}) {
  const items: [ProjectTab, string, IconName][] = [
    ["design", "Overview", "overview"],
    ["model", "Model", "model"],
    ["timing", "Timing", "timing"],
    ["layout", "Layout", "layout"],
    ["parts", "Parts", "parts"],
    ["docs", "Documents", "docs"],
    ["plc", "PLC", "plc"],
    ["revisions", `Revisions (${revisionCount})`, "history"],
  ];
  return (
    <>
      <div className="sidebar-label">Current project</div>
      <div className="sidebar-project">
        <strong title={name}>{name}</strong>
        <span>Machine concept</span>
      </div>
      <nav className="project-nav" aria-label="Project">
        {items.map(([key, label, icon]) => (
          <button key={key} onClick={() => onNavigate(key)} aria-current={key === tab ? "page" : undefined}>
            <Icon name={icon} />
            <span>{label}</span>
            {key === tab && <Icon name="arrow" size={15} />}
          </button>
        ))}
      </nav>
    </>
  );
}
