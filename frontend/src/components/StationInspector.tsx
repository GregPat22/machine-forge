import { useEffect, useRef } from "react";
import type { Station } from "../types";
import Icon from "./Icon";

const number = (value: number | null, unit: string) =>
  value === null ? "Not specified" : `${value.toLocaleString("en-GB")} ${unit}`;
export default function StationInspector({
  station,
  onClose,
  onEdit,
  readOnly,
}: {
  station: Station | null;
  onClose: () => void;
  onEdit: (id: string) => void;
  readOnly: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (station && !dialog.current?.open) dialog.current?.showModal();
    else if (!station) dialog.current?.close();
  }, [station]);
  return (
    <dialog
      className="station-dialog"
      ref={dialog}
      aria-labelledby="station-inspector-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) dialog.current?.close();
      }}
    >
      {station && (
        <>
          <header className="dialog-heading">
            <div>
              <p className="eyebrow">{station.kind}</p>
              <h2 id="station-inspector-title">{station.name}</h2>
            </div>
            <button className="icon-button" aria-label="Close station details" onClick={() => dialog.current?.close()}>
              <Icon name="close" />
            </button>
          </header>
          <div className="dialog-content">
            <p className="mono muted text-xs">{station.id}</p>
            <p className="mt-3 text-sm muted">{station.function}</p>
            <div className="inspector-facts">
              {(
                [
                  ["Length", station.length_mm],
                  ["Width", station.width_mm],
                  ["Height", station.height_mm],
                ] as const
              ).map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{number(value, "mm")}</strong>
                </div>
              ))}
            </div>
            <section className="inspector-section">
              <h3>Mechanisms</h3>
              {station.mechanisms.length ? (
                station.mechanisms.map((axis) => (
                  <div key={axis.id} className="inspector-axis">
                    <strong className="mono text-xs">{axis.id}</strong>
                    <dl>
                      <div>
                        <dt>Stroke</dt>
                        <dd>{number(axis.stroke, axis.kind === "linear" ? "mm" : "deg")}</dd>
                      </div>
                      <div>
                        <dt>Max speed</dt>
                        <dd>{number(axis.max_speed, axis.kind === "linear" ? "mm/s" : "deg/s")}</dd>
                      </div>
                      <div>
                        <dt>Acceleration</dt>
                        <dd>{number(axis.acceleration, axis.kind === "linear" ? "mm/s²" : "deg/s²")}</dd>
                      </div>
                    </dl>
                  </div>
                ))
              ) : (
                <p className="muted text-sm">No mechanisms specified.</p>
              )}
            </section>
            <section className="inspector-section">
              <h3>Components</h3>
              <ul className="inspector-components">
                {station.components.map((component) => (
                  <li key={component.id}>
                    <div>
                      <strong className="font-medium">{component.name}</strong>
                      <p className="muted text-xs mt-1">
                        {component.category} · {component.make_or_buy} · criticality {component.criticality}
                      </p>
                      <p className="muted text-xs mt-1">
                        {[component.manufacturer, component.part_number].filter(Boolean).join(" / ")}
                      </p>
                      {component.specs.map((spec, i) => (
                        <p className="muted text-xs mt-1" key={i}>
                          {spec.name}: {spec.value}
                        </p>
                      ))}
                      <p className="muted text-xs mt-1">
                        {component.wear_part ? "Wear part · " : ""}Recommended spares: {component.recommended_spares}
                      </p>
                    </div>
                    <span className="mono">× {component.quantity}</span>
                  </li>
                ))}
              </ul>
              {!station.components.length && <p className="muted text-sm">No components specified.</p>}
            </section>
            <button className="btn-primary mt-6" onClick={() => onEdit(station.id)}>
              {readOnly ? "View in model editor" : "Open in model editor"}
              <Icon name="external" size={17} />
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}
