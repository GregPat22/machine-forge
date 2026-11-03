import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Layout, MachineDesign, Station } from "../types";
import { projectEnvelopes } from "./conceptProjection";

export default function ConceptPreview({
  projectId,
  revision,
  design,
  selected,
  onSelect,
}: {
  projectId: string;
  revision: number;
  design: MachineDesign;
  selected: string | null;
  onSelect: (station: Station) => void;
}) {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<"envelopes" | "flow">("envelopes");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    let obsolete = false;
    setLayout(null);
    setError(null);
    if (design.stations.length)
      api
        .layout(projectId, revision)
        .then((result) => {
          if (!obsolete) setLayout(result);
        })
        .catch((e: Error) => {
          if (!obsolete) setError(e.message);
        });
    return () => {
      obsolete = true;
    };
  }, [projectId, revision, attempt, design.stations.length]);
  const flow = design.stations.filter((s) => s.sequence > 0).sort((a, b) => a.sequence - b.sequence);
  const ids = new Set(flow.map((s) => s.id));
  const boxes =
    layout?.boxes
      .filter((box) => box.station_id !== null && ids.has(box.station_id))
      .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0)) ?? [];
  const drawing = projectEnvelopes(boxes);
  const choose = (id: string | null) => {
    const station = design.stations.find((s) => s.id === id);
    if (station) onSelect(station);
  };
  return (
    <section className="card concept-panel" id="concept">
      <div className="panel-heading">
        <div>
          <h2>Machine at a glance</h2>
          <p>Stations along the product flow</p>
        </div>
        <div className="view-switch" role="tablist" aria-label="Machine summary view">
          {(["envelopes", "flow"] as const).map((value, index) => (
            <button
              key={value}
              ref={(el) => {
                tabs.current[index] = el;
              }}
              role="tab"
              id={`concept-${value}-tab`}
              aria-selected={mode === value}
              aria-controls="concept-content"
              tabIndex={mode === value ? 0 : -1}
              onClick={() => setMode(value)}
              onKeyDown={(event) => {
                if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                  event.preventDefault();
                  const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
                  setMode(next === 0 ? "envelopes" : "flow");
                  tabs.current[next]?.focus();
                }
              }}
            >
              {value === "envelopes" ? "Envelopes" : "Flow"}
            </button>
          ))}
        </div>
      </div>
      <div className="concept-visual" id="concept-content" role="tabpanel" aria-labelledby={`concept-${mode}-tab`}>
        {!design.stations.length ? (
          <p className="empty-state">No stations in this concept yet.</p>
        ) : mode === "flow" ? (
          <div className="flow-summary">
            {flow.length ? (
              flow.map((station) => (
                <button className="flow-node" key={station.id} onClick={() => onSelect(station)}>
                  <span className="mono">{station.sequence}</span>
                  <strong>{station.name}</strong>
                  <span>{station.kind}</span>
                </button>
              ))
            ) : (
              <p>No stations are connected to the product flow.</p>
            )}
            {design.transports.length > 0 && (
              <p className="flow-connections">
                {design.transports.map((edge) => (
                  <span key={edge.id}>
                    {design.stations.find((s) => s.id === edge.from_station)?.name ?? edge.from_station} →{" "}
                    {design.stations.find((s) => s.id === edge.to_station)?.name ?? edge.to_station}{" "}
                    <small>({edge.kind})</small>
                  </span>
                ))}
              </p>
            )}
          </div>
        ) : error ? (
          <div className="empty-state">
            <p role="alert">{error}</p>
            <button className="btn-secondary mt-3" onClick={() => setAttempt((n) => n + 1)}>
              Retry layout
            </button>
          </div>
        ) : !layout ? (
          <p className="empty-state" role="status">
            Loading the concept layout…
          </p>
        ) : !boxes.length ? (
          <p className="empty-state">
            No stations are connected to the product flow. Open the model to review transports.
          </p>
        ) : (
          <svg
            data-testid="concept-preview"
            className="machine-svg"
            viewBox={drawing.viewBox}
            aria-label="Concept envelopes from the layout; not manufacturing geometry"
          >
            {drawing.envelopes.map(({ box, side, front, top, label }) => (
              <g
                key={box.id}
                className={`envelope ${selected === box.station_id ? "selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`Inspect ${box.label}`}
                onClick={() => choose(box.station_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    choose(box.station_id);
                  }
                }}
                data-length-mm={box.length}
                data-width-mm={box.width}
                data-height-mm={box.height}
              >
                <title>
                  {box.label}: {box.length} × {box.width} × {box.height} mm
                </title>
                <polygon className="face-side" points={side} />
                <polygon className="face-front" points={front} />
                <polygon className="face-top" points={top} />
                <text x={label[0]} y={label[1]} fontSize={drawing.fontSize}>
                  {box.sequence}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>
      {flow.length > 0 && (
        <div className="station-legend">
          {flow.map((station) => (
            <button
              key={station.id}
              className={selected === station.id ? "selected" : ""}
              onClick={() => onSelect(station)}
              title={station.name}
            >
              <span className="mono">{String(station.sequence).padStart(2, "0")}</span>
              <span>{station.name}</span>
            </button>
          ))}
        </div>
      )}
      <div className="concept-foot">
        <span>Concept envelopes · sizes and positions from the layout</span>
        <span className="mono">{flow.length} flow stations</span>
      </div>
    </section>
  );
}
