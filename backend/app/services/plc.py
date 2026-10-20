"""IEC 61131-3 Structured Text skeleton generated from the design.

What it produces:
- E_PackMLState / E_PackMLCmd enums and FB_PackML, a simplified PackML (ISA-TR88.00.02) state machine;
- GVL_IO with one variable per estimated I/O point;
- one function block per flow station with a step sequence for its actuators;
- PRG_Main, which passes HMI commands to the stations and chains their cycles.

Exports: plain .st files (zip) and PLCopen XML (TC6 v2.01) for CODESYS-based IDEs and TwinCAT.
Safety functions are deliberately NOT generated: they belong in a safety PLC or relay, designed and
validated by a qualified engineer.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel

from app.models import MachineDesign, Station
from app.services.documents import safety_function_rows
from app.services.io_points import IOPoint, io_points, station_codes

ELEMENTARY = {"BOOL", "INT", "DINT", "UINT", "REAL", "TIME", "WORD", "BYTE"}
IEC_TYPE = {"DI": "BOOL", "DO": "BOOL", "Safety DI": "BOOL", "AI": "INT", "AO": "INT"}

PACKML_STATES = [
    ("UNDEFINED", 0), ("CLEARING", 1), ("STOPPED", 2), ("STARTING", 3), ("IDLE", 4), ("SUSPENDED", 5),
    ("EXECUTE", 6), ("STOPPING", 7), ("ABORTING", 8), ("ABORTED", 9), ("HOLDING", 10), ("HELD", 11),
    ("UNHOLDING", 12), ("SUSPENDING", 13), ("UNSUSPENDING", 14), ("RESETTING", 15), ("COMPLETING", 16),
    ("COMPLETE", 17),
]
PACKML_CMDS = [
    ("NONE", 0), ("RESET", 1), ("START", 2), ("STOP", 3), ("HOLD", 4), ("UNHOLD", 5), ("SUSPEND", 6),
    ("UNSUSPEND", 7), ("ABORT", 8), ("CLEAR", 9),
]
ACTING_STATES = ("RESETTING", "STARTING", "STOPPING", "HOLDING", "UNHOLDING", "SUSPENDING", "UNSUSPENDING",
                 "ABORTING")


@dataclass
class Var:
    name: str
    type: str
    init: str | None = None
    comment: str | None = None


@dataclass
class Pou:
    name: str
    kind: str  # "functionBlock" | "program"
    comment: str
    body: str
    inputs: list[Var] = field(default_factory=list)
    outputs: list[Var] = field(default_factory=list)
    locals: list[Var] = field(default_factory=list)
    constants: list[Var] = field(default_factory=list)


@dataclass
class EnumType:
    name: str
    values: list[tuple[str, int]]
    comment: str


class PlcFile(BaseModel):
    name: str
    content: str


class PlcProject(BaseModel):
    name: str
    files: list[PlcFile]
    io_counts: dict[str, int]
    axes: list[str]
    warnings: list[str]


# --- helpers ---------------------------------------------------------------------------------------


def identifier(text: str, prefix: str = "") -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    name = prefix + "".join(w[:1].upper() + w[1:] for w in words)
    return name[:60] or f"{prefix}Unnamed"


def _comment(text: str) -> str:
    return text.replace("(*", "( *").replace("*)", "* )")


def _var_line(v: Var) -> str:
    line = f"    {v.name} : {v.type}" + (f" := {v.init}" if v.init else "") + ";"
    return line + (f" (* {_comment(v.comment)} *)" if v.comment else "")


# --- generation ------------------------------------------------------------------------------------


def _packml_fb() -> Pou:
    transitions = {
        "STOPPED": [("eCmd = E_PackMLCmd.RESET", "RESETTING")],
        "IDLE": [("eCmd = E_PackMLCmd.START", "STARTING"), ("eCmd = E_PackMLCmd.STOP", "STOPPING")],
        "EXECUTE": [("eCmd = E_PackMLCmd.HOLD", "HOLDING"), ("eCmd = E_PackMLCmd.SUSPEND", "SUSPENDING"),
                    ("eCmd = E_PackMLCmd.STOP", "STOPPING")],
        "HELD": [("eCmd = E_PackMLCmd.UNHOLD", "UNHOLDING"), ("eCmd = E_PackMLCmd.STOP", "STOPPING")],
        "SUSPENDED": [("eCmd = E_PackMLCmd.UNSUSPEND", "UNSUSPENDING"), ("eCmd = E_PackMLCmd.STOP", "STOPPING")],
        "ABORTED": [("eCmd = E_PackMLCmd.CLEAR", "CLEARING")],
        "RESETTING": [("bActingDone", "IDLE")],
        "STARTING": [("bActingDone", "EXECUTE")],
        "HOLDING": [("bActingDone", "HELD")],
        "UNHOLDING": [("bActingDone", "EXECUTE")],
        "SUSPENDING": [("bActingDone", "SUSPENDED")],
        "UNSUSPENDING": [("bActingDone", "EXECUTE")],
        "STOPPING": [("bActingDone", "STOPPED")],
        "ABORTING": [("bActingDone", "ABORTED")],
        "CLEARING": [("bActingDone", "STOPPED")],
    }
    lines = [
        "(* Any state except Aborting/Aborted/Clearing goes to Aborting on an abort condition.",
        "   Clearing is excluded so the station can reset its latched fault. *)",
        "IF (bAbort OR eCmd = E_PackMLCmd.ABORT)",
        "   AND eState <> E_PackMLState.ABORTING AND eState <> E_PackMLState.ABORTED",
        "   AND eState <> E_PackMLState.CLEARING THEN",
        "    eState := E_PackMLState.ABORTING;",
        "END_IF",
        "",
        "CASE eState OF",
    ]
    for state, moves in transitions.items():
        lines.append(f"    E_PackMLState.{state}:")
        for i, (cond, target) in enumerate(moves):
            kw = "IF" if i == 0 else "ELSIF"
            lines.append(f"        {kw} {cond} THEN")
            lines.append(f"            eState := E_PackMLState.{target};")
        lines.append("        END_IF")
    lines.append("END_CASE")
    return Pou(
        name="FB_PackML",
        kind="functionBlock",
        comment="Simplified PackML state machine (ISA-TR88.00.02). Completing/Complete are not used.",
        inputs=[Var("eCmd", "E_PackMLCmd", comment="command from the machine mode manager"),
                Var("bAbort", "BOOL", comment="fault or abort condition"),
                Var("bActingDone", "BOOL", comment="the station finished the current acting state")],
        outputs=[Var("eState", "E_PackMLState", "E_PackMLState.STOPPED")],
        body="\n".join(lines),
    )


def _station_fb(code: str, station: Station, points: list[IOPoint]) -> tuple[Pou, list[str]]:
    by_comp: dict[tuple[str, int], dict[str, str]] = {}
    for p in points:
        by_comp.setdefault((p.component.id, p.unit), {})[f"{p.kind}:{p.description}"] = p.variable

    steps: list[str] = []
    home: list[str] = []
    continuous: list[str] = []
    axes: list[str] = []
    done_flags: list[Var] = []
    step = 10

    def add(*lines: str) -> None:
        steps.extend(lines)

    for comp in station.components:
        for unit in range(1, comp.quantity + 1):
            sig = by_comp.get((comp.id, unit), {})
            label = comp.name + (f" #{unit}" if comp.quantity > 1 else "")
            coil, ret, ext = sig.get("DO:valve coil"), sig.get("DI:end position 1"), sig.get("DI:end position 2")
            if coil and ret and ext:
                add(f"        {step}: (* {_comment(label)}: extend *)", f"            {coil} := TRUE;",
                    f"            nStep := {step + 1};",
                    f"        {step + 1}: IF {ext} THEN nStep := {step + 10}; END_IF",
                    f"        {step + 10}: (* {_comment(label)}: retract *)", f"            {coil} := FALSE;",
                    f"            nStep := {step + 11};",
                    f"        {step + 11}: IF {ret} THEN nStep := {step + 20}; END_IF")
                home.append(f"        {coil} := FALSE; (* {_comment(label)} home *)")
                step += 20
            elif (vac := sig.get("DO:vacuum on")) and (vsw := sig.get("DI:vacuum switch")):
                add(f"        {step}: (* {_comment(label)}: grip *)", f"            {vac} := TRUE;",
                    f"            nStep := {step + 1};",
                    f"        {step + 1}: IF {vsw} THEN nStep := {step + 10}; END_IF",
                    f"        {step + 10}: (* TODO: transfer the product, then release *)",
                    f"            {vac} := FALSE;", f"            nStep := {step + 20};")
                home.append(f"        {vac} := FALSE;")
                step += 20
            elif (trig := sig.get("DO:trigger")) and (ok := sig.get("DI:result OK")):
                add(f"        {step}: (* {_comment(label)}: trigger *)", f"            {trig} := TRUE;",
                    f"            nStep := {step + 1};",
                    f"        {step + 1}: IF {ok} THEN {trig} := FALSE; nStep := {step + 10}; END_IF",
                    "            (* TODO: on a NOK result set the reject flag instead of timing out *)")
                home.append(f"        {trig} := FALSE;")
                step += 10
            elif axis := sig.get("Axis:servo axis") or sig.get("Axis:linear axis"):
                flag = f"b{identifier(axis.split('_', 1)[-1])}Done"
                done_flags.append(Var(flag, "BOOL", comment=f"set by the motion block of {label}"))
                axes.append(axis)
                add(f"        {step}: (* {_comment(label)}: TODO move the axis with your motion library,",
                    "               e.g. MC_MoveRelative or a cam profile on the master axis *)",
                    f"            IF {flag} THEN nStep := {step + 10}; END_IF")
                step += 10
            elif dose := sig.get("DO:dispense"):
                add(f"        {step}: (* {_comment(label)}: dispense, TODO dose time *)", f"            {dose} := TRUE;",
                    f"            nStep := {step + 10};",
                    f"        {step + 10}: {dose} := FALSE;", f"            nStep := {step + 20};")
                home.append(f"        {dose} := FALSE;")
                step += 20
            for key, var in sig.items():
                if key in ("DO:run", "DO:heater (SSR)"):
                    what = "TODO: temperature control (PID)" if "heater" in key else "runs in Execute"
                    continuous.append(f"{var} := (eState = E_PackMLState.EXECUTE); (* {_comment(label)}: {what} *)")

    if not steps:
        add(f"        {step}: (* TODO: no actuated components detected for this station *)",
            f"            nStep := {step + 10};")
        step += 10
    last = step

    acting = ", ".join(f"E_PackMLState.{s}" for s in ACTING_STATES)
    body = [
        f"(* Station {code}: {_comment(station.name)}",
        f"   Function: {_comment(station.function)}",
        f"   Target cycle time: {station.cycle_time_s if station.cycle_time_s else 'to be defined'} s *)",
        "",
        "fbPackML(eCmd := eCmd, bAbort := bFault OR bAbortAll, bActingDone := bActingDone);",
        "eState := fbPackML.eState;",
        "bActingDone := FALSE;",
        "bCycleDone := FALSE;",
        "",
        "(* Step timeout: waiting steps (ending in 1) must complete within T_STEP_TIMEOUT. *)",
        "IF nStep <> nLastStep THEN",
        "    tonStep(IN := FALSE);",
        "    nLastStep := nStep;",
        "END_IF",
        "tonStep(IN := (nStep MOD 10) = 1, PT := T_STEP_TIMEOUT);",
        "",
        *continuous,
        *([""] if continuous else []),
        "CASE eState OF",
        f"    {acting}:",
        "        (* TODO: bring the station to its home position, then confirm *)",
        *home,
        "        nStep := 0;",
        "        bActingDone := TRUE;",
        "    E_PackMLState.CLEARING:",
        "        bFault := FALSE;",
        "        nFaultCode := 0;",
        "        bActingDone := TRUE;",
        "    E_PackMLState.EXECUTE:",
        "        CASE nStep OF",
        "        0: (* wait for the cycle trigger (previous station or master axis) *)",
        "            IF bCycleTrigger THEN nStep := 10; END_IF",
        *steps,
        f"        {last}: (* cycle complete *)",
        "            bCycleDone := TRUE;",
        "            nStep := 0;",
        "        END_CASE",
        "        IF tonStep.Q THEN",
        "            bFault := TRUE;",
        "            nFaultCode := nStep;",
        "        END_IF",
        "END_CASE",
    ]
    pou = Pou(
        name=identifier(station.name, f"FB_{code}_"),
        kind="functionBlock",
        comment=f"Station {code}: {station.name}",
        inputs=[Var("eCmd", "E_PackMLCmd"), Var("bAbortAll", "BOOL", comment="abort from the machine"),
                Var("bCycleTrigger", "BOOL", comment="start one cycle")],
        outputs=[Var("eState", "E_PackMLState"), Var("bFault", "BOOL"), Var("nFaultCode", "INT"),
                 Var("bCycleDone", "BOOL", comment="one-cycle pulse when the sequence completes")],
        locals=[Var("fbPackML", "FB_PackML"), Var("nStep", "INT"), Var("nLastStep", "INT"),
                Var("tonStep", "TON"), Var("bActingDone", "BOOL"), *done_flags],
        constants=[Var("T_STEP_TIMEOUT", "TIME", "T#2S", "max time for a waiting step")],
        body="\n".join(body),
    )
    return pou, axes


def _main(stations: list[tuple[str, Pou]], design: MachineDesign) -> Pou:
    instances = [(f"fb{code}", pou) for code, pou in stations]
    body = [
        "(* Machine mode manager. Commands come from the HMI; edge detection (R_TRIG) and the",
        "   PackML unit/module aggregation rules are left to the project. *)",
        "eCmd := E_PackMLCmd.NONE;",
        "IF bCmdAbort THEN eCmd := E_PackMLCmd.ABORT;",
        "ELSIF bCmdStop THEN eCmd := E_PackMLCmd.STOP;",
        "ELSIF bCmdClear THEN eCmd := E_PackMLCmd.CLEAR;",
        "ELSIF bCmdReset THEN eCmd := E_PackMLCmd.RESET;",
        "ELSIF bCmdStart THEN eCmd := E_PackMLCmd.START;",
        "ELSIF bCmdHold THEN eCmd := E_PackMLCmd.HOLD;",
        "ELSIF bCmdUnhold THEN eCmd := E_PackMLCmd.UNHOLD;",
        "END_IF",
        "",
    ]
    if instances:
        faults = " OR ".join(f"{name}.bFault" for name, _ in instances)
        body += [f"bAnyFault := {faults};", ""]
        previous = "TRUE (* TODO: machine cycle / master axis *)"
        for name, _pou in instances:
            body.append(f"{name}(eCmd := eCmd, bAbortAll := bAnyFault, bCycleTrigger := {previous});")
            previous = f"{name}.bCycleDone"
        body += ["", f"eMachineState := {instances[0][0]}.eState; (* TODO: aggregate the station states *)"]
    body += ["", "(* SAFETY: the safety functions below are NOT implemented in this program.",
             "   Implement them in a safety PLC or safety relay and validate them (ISO 13849-1). *)"]
    body += [f"(*   - {_comment(row[0])}: {_comment(row[1])} -> {_comment(row[2])} *)"
             for row in safety_function_rows(design)]
    return Pou(
        name="PRG_Main",
        kind="program",
        comment=f"Main program for {design.name}",
        locals=[Var(n, "BOOL", comment="HMI command") for n in
                ("bCmdReset", "bCmdStart", "bCmdStop", "bCmdHold", "bCmdUnhold", "bCmdAbort", "bCmdClear")]
        + [Var("eCmd", "E_PackMLCmd"), Var("eMachineState", "E_PackMLState"), Var("bAnyFault", "BOOL")]
        + [Var(name, pou.name, comment=pou.comment) for name, pou in instances],
        body="\n".join(body),
    )


def _globals(points: list[IOPoint]) -> list[Var]:
    out = []
    for p in points:
        if p.kind in IEC_TYPE:
            note = f"{p.station.name} / {p.component.name}: {p.description}"
            if p.kind == "Safety DI":
                note += " (status only - safety logic lives in the safety PLC)"
            out.append(Var(p.variable, IEC_TYPE[p.kind], comment=note))
    return out


@dataclass
class _Model:
    enums: list[EnumType]
    pous: list[Pou]
    globals: list[Var]
    axes: list[str]
    fieldbus: list[str]
    warnings: list[str]


def _build(design: MachineDesign) -> _Model:
    points = io_points(design)
    station_pous: list[tuple[str, Pou]] = []
    axes: list[str] = []
    codes = [(c, s) for c, s in station_codes(design) if c.startswith("S")]
    for code, station in codes:
        pou, station_axes = _station_fb(code, station, [p for p in points if p.station.id == station.id])
        station_pous.append((code, pou))
        axes += station_axes
    warnings = ["Skeleton only: review every step, timeout and interlock before running it on a machine.",
                "No safety logic is generated. Safety functions belong in a safety PLC or relay."]
    if not codes:
        warnings.append("The design has no flow stations, so no station function blocks were generated.")
    return _Model(
        enums=[EnumType("E_PackMLState", PACKML_STATES, "PackML states (ISA-TR88.00.02)"),
               EnumType("E_PackMLCmd", PACKML_CMDS, "PackML commands")],
        pous=[_packml_fb(), *(p for _, p in station_pous), _main(station_pous, design)],
        globals=_globals(points),
        axes=axes,
        fieldbus=[f"{p.variable}: {p.station.name} / {p.component.name}" for p in points if p.kind == "Fieldbus"],
        warnings=warnings,
    )


# --- structured text -----------------------------------------------------------------------------


def _enum_st(e: EnumType) -> str:
    values = ",\n".join(f"    {n} := {v}" for n, v in e.values)
    return f"(* {e.comment} *)\nTYPE {e.name} :\n(\n{values}\n);\nEND_TYPE\n"


def _pou_st(p: Pou) -> str:
    head = "FUNCTION_BLOCK" if p.kind == "functionBlock" else "PROGRAM"
    lines = [f"{head} {p.name}", f"(* {_comment(p.comment)} *)"]
    for section, vars_ in (("VAR_INPUT", p.inputs), ("VAR_OUTPUT", p.outputs), ("VAR", p.locals),
                           ("VAR CONSTANT", p.constants)):
        if vars_:
            lines += [section, *(_var_line(v) for v in vars_), "END_VAR"]
    lines += ["", p.body, f"END_{head}", ""]
    return "\n".join(lines)


def _gvl_st(model: _Model) -> str:
    lines = ["(* Estimated I/O. Map each variable to your hardware addresses. *)", "VAR_GLOBAL"]
    lines += [_var_line(v) for v in model.globals]
    lines.append("END_VAR")
    if model.axes:
        lines += ["", "(* Servo / linear axes: declare them with your motion library's axis type",
                  "   (e.g. AXIS_REF_SM3 in CODESYS SoftMotion, AXIS_REF in TwinCAT NC): *)"]
        lines += [f"(*   {a} *)" for a in model.axes]
    if model.fieldbus:
        lines += ["", "(* Fieldbus devices (PROFINET / EtherCAT / EtherNet/IP): *)"]
        lines += [f"(*   {_comment(f)} *)" for f in model.fieldbus]
    return "\n".join(lines) + "\n"


def generate(design: MachineDesign, revision: int) -> PlcProject:
    model = _build(design)
    files = [PlcFile(name=f"{e.name}.st", content=_enum_st(e)) for e in model.enums]
    files.append(PlcFile(name="GVL_IO.st", content=_gvl_st(model)))
    files += [PlcFile(name=f"{p.name}.st", content=_pou_st(p)) for p in model.pous]
    counts: dict[str, int] = {}
    for p in io_points(design):
        counts[p.kind] = counts.get(p.kind, 0) + 1
    return PlcProject(name=f"{design.name} (revision {revision})", files=files, io_counts=counts,
                      axes=model.axes, warnings=model.warnings)


def to_zip(project: PlcProject, design: MachineDesign) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in project.files:
            zf.writestr(f"st/{f.name}", f.content)
        zf.writestr("plcopen.xml", to_plcopen_xml(design, project.name))
        zf.writestr("README.txt", "\n".join([
            f"PLC skeleton for {project.name}", "",
            "st/          one Structured Text file per type, variable list and POU (copy into your IDE)",
            "plcopen.xml  the same project as PLCopen XML (TC6 v2.01), for IDEs that import it",
            "", *project.warnings, "",
        ]))
    return buffer.getvalue()


# --- PLCopen XML (TC6 v2.01) -----------------------------------------------------------------------

XHTML = "http://www.w3.org/1999/xhtml"


def _type_xml(type_name: str) -> str:
    return f"<{type_name}/>" if type_name in ELEMENTARY else f"<derived name={quoteattr(type_name)}/>"


def _var_xml(v: Var) -> str:
    xml = f"<variable name={quoteattr(v.name)}><type>{_type_xml(v.type)}</type>"
    if v.init:
        xml += f"<initialValue><simpleValue value={quoteattr(v.init)}/></initialValue>"
    if v.comment:
        xml += f'<documentation><xhtml xmlns="{XHTML}">{escape(v.comment)}</xhtml></documentation>'
    return xml + "</variable>"


def _vars_xml(tag: str, vars_: list[Var], attrs: str = "") -> str:
    if not vars_:
        return ""
    return f"<{tag}{attrs}>" + "".join(_var_xml(v) for v in vars_) + f"</{tag}>"


def to_plcopen_xml(design: MachineDesign, project_name: str) -> str:
    model = _build(design)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    data_types = "".join(
        f"<dataType name={quoteattr(e.name)}><baseType><enum><values>"
        + "".join(f"<value name={quoteattr(n)} value={quoteattr(str(v))}/>" for n, v in e.values)
        + f'</values></enum></baseType><documentation><xhtml xmlns="{XHTML}">{escape(e.comment)}</xhtml>'
        "</documentation></dataType>"
        for e in model.enums
    )
    pous = "".join(
        f"<pou name={quoteattr(p.name)} pouType={quoteattr(p.kind)}><interface>"
        + _vars_xml("inputVars", p.inputs) + _vars_xml("outputVars", p.outputs)
        + _vars_xml("localVars", p.locals) + _vars_xml("localVars", p.constants, ' constant="true"')
        + f'</interface><body><ST><xhtml xmlns="{XHTML}">{escape(p.body)}</xhtml></ST></body>'
        f'<documentation><xhtml xmlns="{XHTML}">{escape(p.comment)}</xhtml></documentation></pou>'
        for p in model.pous
    )
    scaling = '<scaling x="1" y="1"/>'
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<project xmlns="http://www.plcopen.org/xml/tc6_0201">'
        f'<fileHeader companyName="Machine Forge" productName="Machine Forge" productVersion="0.3" '
        f'creationDateTime="{now}"/>'
        f"<contentHeader name={quoteattr(project_name)} modificationDateTime=\"{now}\">"
        f"<coordinateInfo><fbd>{scaling}</fbd><ld>{scaling}</ld><sfc>{scaling}</sfc></coordinateInfo>"
        "</contentHeader>"
        f"<types><dataTypes>{data_types}</dataTypes><pous>{pous}</pous></types>"
        '<instances><configurations><configuration name="Config"><resource name="Resource">'
        '<task name="MainTask" priority="1" interval="T#10MS"><pouInstance name="Main" typeName="PRG_Main"/></task>'
        + (f'<globalVars name="GVL_IO">' + "".join(_var_xml(v) for v in model.globals) + "</globalVars>"
           if model.globals else "")
        + "</resource></configuration></configurations></instances></project>\n"
    )
