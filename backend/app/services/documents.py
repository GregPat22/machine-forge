"""Technical documents derived from the design: functional description, sequence of operations,
I/O list, spare parts, hazard checklist (ISO 12100) and safety functions to specify.

Everything here is computed by rules from the machine model, so the documents stay consistent
with the design and never invent compliance claims. The rules are deliberately simple estimates;
the document says so.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime, timezone

from pydantic import BaseModel

from app.models import Component, MachineDesign, Station
from app.services.layout import compute_layout
from app.services.spare_parts import build_catalog

DISCLAIMER = (
    "Draft generated from the concept design. It is not a risk assessment and does not state "
    "conformity with any regulation or standard. A qualified engineer must complete, verify and "
    "approve it (ISO 12100 risk assessment, ISO 13849-1 / IEC 62061 for safety functions, "
    "EU Machinery Regulation 2023/1230 technical file)."
)

SIGNAL_TYPES = ("DI", "DO", "AI", "AO", "Safety DI", "Axis", "Fieldbus")


class DocTable(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class DocSection(BaseModel):
    id: str
    title: str
    paragraphs: list[str] = []
    bullets: list[str] = []
    table: DocTable | None = None
    note: str | None = None


class TechnicalDocument(BaseModel):
    title: str
    subtitle: str
    revision: int
    generated_at: datetime
    disclaimer: str
    io_summary: dict[str, int]
    sections: list[DocSection]


# --- I/O list ---------------------------------------------------------------------------------


def _text(component: Component) -> str:
    return " ".join([component.name, *(f"{s.name} {s.value}" for s in component.specs)]).lower()


def _signals(component: Component) -> list[tuple[str, str]]:
    """(signal type, description) for ONE unit of the component. Heuristic, per category."""
    text = _text(component)
    c = component.category
    if c == "sensor":
        if any(k in text for k in ("thermocouple", "pt100", "load cell", "analog", "4-20", "pressure transmitter")):
            return [("AI", "measurement")]
        return [("DI", "signal")]
    if c == "pneumatic_actuator":
        return [("DO", "valve coil"), ("DI", "end position 1"), ("DI", "end position 2")]
    if c == "vacuum":
        if "ejector" in text or "generator" in text or "pump" in text:
            return [("DO", "vacuum on"), ("DI", "vacuum switch")]
        return []
    if c == "servo_motor":
        return [("Axis", "servo axis")]
    if c == "linear_motion":
        return [("Axis", "linear axis")] if "axis" in text else []
    if c == "motor":
        return [("DO", "run"), ("DI", "running / overload")]
    if c in ("heating", "sealing"):
        return [("DO", "heater (SSR)")] if any(k in text for k in ("heat", "kw", "power", "temp")) else []
    if c in ("pump", "dosing"):
        if "gun" in text:
            return [("DO", "dispense")]
        if any(k in text for k in ("tube", "tubing", "brush")):
            return []  # consumables, or driven by a motor listed separately
        return [("DO", "run"), ("DI", "ready / fault")]
    if c == "safety":
        if any(k in text for k in ("door", "interlock", "switch", "e-stop", "emergency", "light curtain", "scanner")):
            return [("Safety DI", "channel A"), ("Safety DI", "channel B")]
        if "relay" in text:
            return [("DI", "safety relay status"), ("DO", "safety relay reset")]
        return []
    if c in ("vision", "printing_marking"):
        if any(k in text for k in ("camera", "printer", "marking", "laser", "inkjet")):
            return [("Fieldbus", "device"), ("DO", "trigger"), ("DI", "result OK")]
        return []
    if c in ("pneumatic_valve", "drive", "hmi", "io_module"):
        if c == "pneumatic_valve" and "terminal" not in text and "island" not in text:
            return [("DO", "valve coil")]
        return [("Fieldbus", "node")]
    if c == "air_treatment":
        return [("DO", "soft-start / dump valve"), ("DI", "pressure switch")]
    if c == "cooling":
        return [("DO", "run"), ("DI", "fault")]
    return []


def io_list(design: MachineDesign) -> tuple[list[list[str]], Counter[str]]:
    rows: list[list[str]] = []
    totals: Counter[str] = Counter()
    for code, station in _station_codes(design):
        for component in station.components:
            per_unit = _signals(component)
            for unit in range(1, component.quantity + 1):
                per_type: Counter[str] = Counter()
                for kind, desc in per_unit:
                    per_type[kind] += 1
                    suffix = f".{unit}" if component.quantity > 1 else ""
                    tag = f"{code}.{component.id}{suffix}.{kind.replace(' ', '')}{per_type[kind]}"
                    rows.append([tag, station.name, component.name, kind, desc])
                    totals[kind] += 1
    return rows, totals


def _station_codes(design: MachineDesign) -> list[tuple[str, Station]]:
    flow = sorted((s for s in design.stations if s.sequence > 0), key=lambda s: s.sequence)
    infra = [s for s in design.stations if s.sequence <= 0]
    return [(f"S{s.sequence:02d}", s) for s in flow] + [(f"X{i:02d}", s) for i, s in enumerate(infra, start=1)]


# --- hazards and safety functions ----------------------------------------------------------------

# category -> (ISO 12100 hazard group, hazard, proposed protective measure)
HAZARDS: dict[str, tuple[str, str, str]] = {
    "servo_motor": ("Mechanical", "Crushing / shearing by moving mechanisms",
                    "Fixed or interlocked guards; Safe Torque Off on guard opening"),
    "motor": ("Mechanical", "Entanglement / drawing-in by rotating parts",
              "Fixed guards on transmissions; interlocked access"),
    "gearbox": ("Mechanical", "Entanglement by rotating shafts and couplings", "Fixed guards on shafts and couplings"),
    "transmission": ("Mechanical", "Drawing-in at belts, chains and pulleys", "Fixed guards; nip-point protection"),
    "conveyor": ("Mechanical", "Drawing-in at conveyor nip points and transfers", "Nip guards; emergency stop within reach"),
    "linear_motion": ("Mechanical", "Crushing / impact by moving axes", "Interlocked guards; reduced speed in setup mode"),
    "cutting": ("Mechanical", "Cutting / severing", "Interlocked guards with guard locking; two-hand control for setup"),
    "pneumatic_actuator": ("Mechanical", "Crushing by pneumatic actuators; stored pneumatic energy",
                           "Guards; pneumatic dump valve and lockable isolation"),
    "vacuum": ("Mechanical", "Unexpected release of parts on vacuum loss", "Vacuum monitoring; safe state on loss"),
    "heating": ("Thermal", "Burns from hot surfaces", "Insulation, guards, warning signs; heaters off on guard opening"),
    "sealing": ("Thermal", "Burns from heated sealing tools", "Guards; heaters off or retracted on guard opening"),
    "electrical": ("Electrical", "Contact with live parts", "IP2X protection, cabinet interlock, IEC 60204-1 design"),
    "drive": ("Electrical", "Stored energy in drive DC bus", "Discharge time warning; lockable isolation"),
    "pump": ("Material / substance", "Contact with product or cleaning agents", "Closed system; safety data sheets; PPE"),
    "dosing": ("Material / substance", "Contact with product, dosing media or adhesives",
               "Shielding; PPE; temperature limits for hot melt"),
    "vision": ("Radiation", "Optical radiation from lighting / lasers", "Check photobiological safety (IEC 62471) or laser class"),
    "printing_marking": ("Radiation", "Laser or UV radiation from marking units", "Enclosure; laser safety per IEC 60825-1"),
}
GENERAL_HAZARDS = [
    ("Noise", "Noise emission of the machine", "Measure emission; enclose noisy units"),
    ("Ergonomic", "Format changeover, cleaning and maintenance postures",
     "Tool-less changeover, access heights, lifting aids for heavy format parts"),
    ("Combination", "Unexpected start-up during intervention", "Lockout/tagout points; safe stop and restart logic"),
]


def hazard_rows(design: MachineDesign) -> list[list[str]]:
    rows: list[list[str]] = []
    for _code, station in _station_codes(design):
        seen: set[str] = set()
        for component in station.components:
            hazard = HAZARDS.get(component.category)
            if hazard is None or hazard[1] in seen:
                continue
            seen.add(hazard[1])
            group, text, measure = hazard
            rows.append([station.name, group, text, component.name, measure, "to assess"])
    rows.extend(["Whole machine", group, text, "—", measure, "to assess"] for group, text, measure in GENERAL_HAZARDS)
    return rows


def safety_function_rows(design: MachineDesign) -> list[list[str]]:
    categories = {c.category for s in design.stations for c in s.components}
    rows = [["Emergency stop", "E-stop pressed", "Stop category 0 or 1 (IEC 60204-1), all hazardous motion"]]
    if any(s.kind == "safety" for s in design.stations) or categories & {"guarding", "safety"}:
        rows.append(["Guard interlocking", "Guard door opened", "Stop hazardous motion; prevent restart until closed and reset"])
    if categories & {"servo_motor", "drive"}:
        rows.append(["Safe Torque Off", "Guard opened or E-stop", "Remove torque from servo drives (STO, IEC 61800-5-2)"])
    if "cutting" in categories or "servo_motor" in categories:
        rows.append(["Guard locking", "Access request while machine runs down",
                     "Keep guards locked until hazardous motion has stopped"])
    if categories & {"pneumatic_actuator", "pneumatic_valve", "air_treatment"}:
        rows.append(["Pneumatic energy isolation", "E-stop or guard opened", "Exhaust pneumatic energy (dump valve), safe actuator state"])
    if categories & {"heating", "sealing"}:
        rows.append(["Heater shutdown / tool retraction", "Guard opened", "Switch off or retract heated tools"])
    rows.append(["Safe setup mode", "Mode selector in setup", "Reduced speed, hold-to-run with enabling device"])
    return [[name, trigger, reaction, "to be determined (ISO 13849-1)"] for name, trigger, reaction in rows]


# --- cycle-time check ---------------------------------------------------------------------------


def cycle_check(design: MachineDesign) -> list[str]:
    timed = [s for s in design.stations if s.sequence > 0 and s.cycle_time_s]
    if not timed:
        return ["No cycle times in the design yet: ask the AI to estimate them."]
    slowest = max(timed, key=lambda s: s.cycle_time_s or 0)
    cycles_per_min = 60 / (slowest.cycle_time_s or 1)
    lines = [f"Slowest station: {slowest.name} at {slowest.cycle_time_s:g} s/cycle, "
             f"so the line can run at most {cycles_per_min:.1f} cycles/min."]
    match = re.search(r"(\d[\d.,]*)\s*([^/]*)/\s*(min|h)", design.throughput or "")
    if match:
        required = float(match.group(1).replace(",", "."))
        per_min = required if match.group(3) == "min" else required / 60
        per_cycle = per_min / cycles_per_min
        unit = match.group(2).strip() or "products"
        lines.append(f"Required throughput {design.throughput} → each cycle must handle at least "
                     f"{per_cycle:.1f} {unit} (multiple lanes or products per cycle).")
    return lines


# --- document assembly --------------------------------------------------------------------------


def build_document(design: MachineDesign, revision: int) -> TechnicalDocument:
    layout = compute_layout(design)
    flow = sorted((s for s in design.stations if s.sequence > 0), key=lambda s: s.sequence)
    io_rows, io_totals = io_list(design)
    parts = build_catalog(design)
    spares = [p for p in parts if p.recommended_spares > 0 or p.wear_part]

    footprint = (
        f"{layout.footprint_length_mm / 1000:.1f} m × {layout.footprint_width_mm / 1000:.1f} m (concept layout)"
        if layout.footprint_length_mm else (design.footprint or "—")
    )
    overview = DocTable(columns=["Property", "Value"], rows=[
        ["Machine type", design.machine_type],
        ["Product", design.product],
        ["Throughput", design.throughput or "to be defined"],
        ["Footprint", footprint],
        ["Layout", "U-shape" if design.layout_style == "u_shape" else "Inline"],
        ["Process stations", str(len(flow))],
        ["Utilities", ", ".join(design.utilities) or "—"],
    ])

    spare_io = {k: v + max(1, round(v * 0.2)) for k, v in io_totals.items() if k in ("DI", "DO", "AI", "AO", "Safety DI")}
    io_summary_text = ", ".join(f"{k}: {io_totals[k]}" for k in SIGNAL_TYPES if io_totals.get(k)) or "no signals"
    sizing = ", ".join(f"{k} {v}" for k, v in spare_io.items())

    sections = [
        DocSection(id="overview", title="1. Machine overview", paragraphs=[design.summary], table=overview),
        DocSection(
            id="functional", title="2. Functional description",
            table=DocTable(columns=["#", "Station", "Function", "Main components"], rows=[
                [str(s.sequence), s.name, s.function,
                 ", ".join(c.name for c in s.components[:4]) + (" …" if len(s.components) > 4 else "")]
                for s in flow
            ]),
        ),
        DocSection(
            id="sequence", title="3. Sequence of operations",
            bullets=[f"{s.name}: {s.function}" + (f" ({s.cycle_time_s:g} s/cycle)" if s.cycle_time_s else "")
                     for s in flow],
            paragraphs=cycle_check(design),
        ),
        DocSection(
            id="io", title="4. I/O list (estimate)",
            paragraphs=[f"Totals — {io_summary_text}.",
                        f"PLC sizing with ~20% spare: {sizing}." if sizing else ""],
            table=DocTable(columns=["Tag", "Station", "Component", "Type", "Description"], rows=io_rows),
            note="Estimated by rules from component categories (e.g. a cylinder = 1 valve output + 2 end-position "
                 "inputs). Review it against the electrical design.",
        ),
        DocSection(id="utilities", title="5. Utilities", bullets=design.utilities or ["To be defined."]),
        DocSection(
            id="spares", title="6. Recommended spare parts",
            table=DocTable(columns=["Item", "Part", "Manufacturer / P/N", "Qty in machine", "Spares", "Crit.", "Wear"], rows=[
                [str(p.item), p.name, " ".join(x for x in (p.manufacturer, p.part_number) if x) or "—",
                 str(p.quantity_in_machine), str(p.recommended_spares), p.criticality, "yes" if p.wear_part else ""]
                for p in spares
            ]),
        ),
        DocSection(
            id="hazards", title="7. Hazard checklist (ISO 12100, draft)",
            table=DocTable(columns=["Where", "Hazard group", "Hazard", "Source", "Proposed measure", "Status"],
                           rows=hazard_rows(design)),
            note="Starting list derived from the components. The risk assessment (estimation, evaluation, "
                 "reduction) is still to be done.",
        ),
        DocSection(
            id="safety", title="8. Safety functions to specify",
            table=DocTable(columns=["Safety function", "Trigger", "Reaction", "Required PL"],
                           rows=safety_function_rows(design)),
            note="Required performance levels come from the risk assessment (ISO 13849-1). Safety logic must be "
                 "designed and validated by a qualified engineer, never generated.",
        ),
        DocSection(
            id="open", title="9. Assumptions and open questions",
            bullets=[f"Assumption: {a}" for a in design.assumptions]
            + [f"Open question: {q}" for q in design.open_questions] or ["None recorded."],
        ),
    ]
    for section in sections:
        section.paragraphs = [p for p in section.paragraphs if p]

    return TechnicalDocument(
        title=design.name,
        subtitle=f"Technical description — revision {revision}",
        revision=revision,
        generated_at=datetime.now(timezone.utc),
        disclaimer=DISCLAIMER,
        io_summary=dict(io_totals),
        sections=sections,
    )


# --- exports -------------------------------------------------------------------------------------


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(doc: TechnicalDocument) -> str:
    out = [f"# {doc.title}", "", f"_{doc.subtitle} · generated {doc.generated_at:%Y-%m-%d %H:%M} UTC_", "",
           f"> {doc.disclaimer}", ""]
    for s in doc.sections:
        out += [f"## {s.title}", ""]
        out += [p + "\n" for p in s.paragraphs]
        if s.bullets:
            out += [f"- {b}" for b in s.bullets] + [""]
        if s.table and s.table.rows:
            out.append("| " + " | ".join(s.table.columns) + " |")
            out.append("|" + "---|" * len(s.table.columns))
            out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in s.table.rows]
            out.append("")
        if s.note:
            out += [f"_{s.note}_", ""]
    return "\n".join(out)


def to_docx(doc: TechnicalDocument) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.styles["Normal"].font.size = Pt(10)
    document.add_heading(doc.title, level=0)
    document.add_paragraph(f"{doc.subtitle} · generated {doc.generated_at:%Y-%m-%d %H:%M} UTC")
    document.add_paragraph(doc.disclaimer).runs[0].italic = True
    for s in doc.sections:
        document.add_heading(s.title, level=1)
        for p in s.paragraphs:
            document.add_paragraph(p)
        for b in s.bullets:
            document.add_paragraph(b, style="List Bullet")
        if s.table and s.table.rows:
            table = document.add_table(rows=1, cols=len(s.table.columns))
            table.style = "Table Grid"
            for cell, title in zip(table.rows[0].cells, s.table.columns):
                cell.text = title
                cell.paragraphs[0].runs[0].bold = True
            for row in s.table.rows:
                for cell, value in zip(table.add_row().cells, row):
                    cell.text = value
        if s.note:
            document.add_paragraph(s.note).runs[0].italic = True
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
