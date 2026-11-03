import { useState } from "react";
import type { MachineDesign } from "../types";
import ConceptPreview from "./ConceptPreview";
import StationInspector from "./StationInspector";
import Icon from "./Icon";

export default function DesignView({
  projectId,
  revision,
  design,
  readOnly,
  onAsk,
  onModel,
}: {
  projectId: string;
  revision: number;
  design: MachineDesign;
  readOnly: boolean;
  onAsk: (question?: string) => void;
  onModel: (stationId?: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const flow = design.stations.filter((s) => s.sequence > 0).sort((a, b) => a.sequence - b.sequence);
  const listed = flow.length ? flow : design.stations;
  const infrastructure = design.stations.filter((s) => s.sequence <= 0);
  const visible = expanded ? listed : listed.slice(0, 3);
  const station = inspecting ? (design.stations.find((s) => s.id === selected) ?? null) : null;
  const inspect = (id: string) => {
    setSelected(id);
    setInspecting(true);
  };
  return (
    <>
      <section className="project-heading">
        <div>
          <div className="eyebrow">Project overview / concept design</div>
          <h1>{design.name}</h1>
          <p>{design.summary}</p>
        </div>
        <div className="heading-actions">
          <button className="btn-primary" onClick={() => onModel()}>
            Open machine model
            <Icon name="external" size={18} />
          </button>
        </div>
      </section>
      <div className="metrics">
        <section className="metric rate">
          <span className="metric-label">Requested production rate</span>
          <strong data-testid="overview-requested-rate">{design.target_rate_text ?? "Not specified"}</strong>
          <span className="metric-note">Target from the production brief</span>
        </section>
        <section className="metric">
          <span className="metric-label">Machine structure</span>
          <strong data-testid="overview-station-count">{design.stations.length}</strong>
          <span className="metric-note">{flow.length} in the product flow</span>
        </section>
        <section className="metric">
          <span className="metric-label">Component lines</span>
          <strong data-testid="overview-component-count">
            {design.stations.reduce((n, s) => n + s.components.length, 0)}
          </strong>
          <span className="metric-note">Before BOM aggregation</span>
        </section>
        <section className="metric question">
          <span className="metric-label">Open questions</span>
          <strong data-testid="overview-question-count">{design.open_questions.length}</strong>
          <span className="metric-note">Engineering inputs to review</span>
        </section>
      </div>
      <div className="overview-grid">
        <div className="overview-primary">
          <ConceptPreview
            projectId={projectId}
            revision={revision}
            design={design}
            selected={selected}
            onSelect={(s) => inspect(s.id)}
          />
          <section className="card station-panel">
            <div className="panel-heading">
              <div>
                <h2>Stations in this concept</h2>
                <p>{flow.length ? "Product flow, in process order" : "Model stations"}</p>
              </div>
              <span className="table-count">{listed.length}</span>
            </div>
            {listed.length > 0 && (
              <table className="station-table">
                <thead>
                  <tr>
                    <th scope="col">No.</th>
                    <th scope="col">Station</th>
                    <th scope="col" className="station-kind">
                      Kind
                    </th>
                    <th scope="col">Lines</th>
                    <th scope="col">
                      <span className="sr-only">Inspect</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((s) => (
                    <tr key={s.id}>
                      <td className="station-order mono">
                        {s.sequence > 0 ? String(s.sequence).padStart(2, "0") : "—"}
                      </td>
                      <td>
                        <button className="station-name" onClick={() => inspect(s.id)}>
                          {s.name}
                        </button>
                        <span className="station-id">{s.id}</span>
                      </td>
                      <td className="station-kind muted">{s.kind}</td>
                      <td className="mono">{s.components.length}</td>
                      <td>
                        <button
                          data-testid={`inspect-${s.id}`}
                          className="row-action"
                          aria-label={`Inspect ${s.name}`}
                          onClick={() => inspect(s.id)}
                        >
                          <Icon name="external" size={18} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="table-footer">
              <span>
                {infrastructure.length > 0
                  ? `${infrastructure.length} infrastructure stations are available in the model editor.`
                  : listed.length
                    ? "Every station is in the product flow."
                    : "Add stations in the model editor to begin."}
              </span>
              {listed.length > 3 && (
                <button className="text-action" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
                  {expanded ? "Show fewer stations" : `Show all ${listed.length} stations`}
                  <Icon name="arrow" size={16} />
                </button>
              )}
            </div>
          </section>
        </div>
        <aside className="overview-secondary" aria-label="Next steps and project details">
          <section className="card attention-panel">
            <div className="attention-label">
              <Icon name="question" size={18} />
              {design.open_questions.length ? "Needs your input" : "Engineering questions"}
            </div>
            <h2>{design.open_questions.length ? "Review the open question." : "Keep the assumptions visible."}</h2>
            <p>{design.open_questions[0] ?? "No open questions recorded."}</p>
            {design.open_questions.length > 0 && (
              <button className="text-action" onClick={() => onAsk(design.open_questions[0])}>
                Review open question
                <Icon name="arrow" size={18} />
              </button>
            )}
            {design.open_questions.length > 1 && (
              <details className="mt-3">
                <summary className="text-xs cursor-pointer">{design.open_questions.length - 1} more questions</summary>
                <ul className="mt-3 space-y-2">
                  {design.open_questions.slice(1).map((q, i) => (
                    <li key={i}>
                      <button className="text-left text-sm text-brand-700" onClick={() => onAsk(q)}>
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
          <section className="card assistant-card">
            <div className="assistant-label">
              <Icon name="spark" size={18} />
              Engineering assistant
            </div>
            <h2>What should change next?</h2>
            <p>Work through a question or describe a change to the machine.</p>
            <button className="btn-secondary" onClick={() => onAsk()}>
              Refine the concept
              <Icon name="arrow" size={18} />
            </button>
          </section>
          <section className="card context-panel">
            <h2>Engineering context</h2>
            <dl>
              <div>
                <dt>Product</dt>
                <dd>{design.product.name ?? design.product.description ?? "Not specified"}</dd>
              </div>
              <div>
                <dt>Machine type</dt>
                <dd>{design.machine_type}</dd>
              </div>
              <div>
                <dt>Wear component lines</dt>
                <dd className="mono">
                  {design.stations.reduce((n, s) => n + s.components.filter((c) => c.wear_part).length, 0)}
                </dd>
              </div>
              {design.footprint && (
                <div>
                  <dt>Declared footprint</dt>
                  <dd>{design.footprint}</dd>
                </div>
              )}
              <div>
                <dt>Line arrangement</dt>
                <dd>{design.layout_style === "u_shape" ? "U-shape" : "Inline"}</dd>
              </div>
              <div>
                <dt>Line throughput</dt>
                <dd>Not evaluated</dd>
              </div>
              <div>
                <dt>Design revision</dt>
                <dd className="mono">
                  {revision}
                  {readOnly ? " / historical" : " / latest"}
                </dd>
              </div>
            </dl>
          </section>
          {(design.assumptions.length > 0 || design.utilities.length > 0) && (
            <details className="overview-assumption">
              <summary>Assumptions ({design.assumptions.length}) & utilities</summary>
              {design.assumptions.map((assumption, i) => (
                <p key={i}>{assumption}</p>
              ))}
              {design.utilities.length > 0 && (
                <>
                  <h3 className="text-sm font-medium mt-4">Utilities</h3>
                  {design.utilities.map((utility, i) => (
                    <p key={i}>{utility}</p>
                  ))}
                </>
              )}
            </details>
          )}
        </aside>
      </div>
      <footer className="page-footer">
        <span>Machine concept · revision {revision}</span>
        <span>Requirements and engineering results are shown separately.</span>
      </footer>
      <StationInspector
        station={station}
        readOnly={readOnly}
        onClose={() => setInspecting(false)}
        onEdit={(id) => {
          setInspecting(false);
          onModel(id);
        }}
      />
    </>
  );
}
