# What should "create the machine" produce?

Status: **options 1 and 4 built in v0.2** (2026-10-20): 3D concept layout and technical documents.
Options 2 (PLC) and 3 (CAD) remain open. This document compares the four candidate outputs.

## What already exists, whatever we choose

Every option below is a *view or export of the same machine model* (`MachineDesign` in
`backend/app/models.py`): stations in product-flow order, each with its function, cycle time and
components (category, specs, manufacturer, part number, make/buy, wear part, criticality,
recommended spares). The AI edits that model on every prompt and keeps revisions.

The prompting loop and the spare-parts catalog need that model anyway, so it was built first (v0.1).
The four options are what we add on top.

```
problem ──> prompts ──> MachineDesign (revisions) ──┬──> spare-parts catalog ──> supplier comparison   (built)
                                                    ├──> 1. 3D layout                                (built, v0.2)
                                                    ├──> 2. PLC control logic                        (open)
                                                    ├──> 3. CAD export (STEP)                        (open)
                                                    └──> 4. specs + safety documents                 (built, v0.2)
```

## Summary

| Option | Value for whom | LLM fit | Effort* | Risk | Verdict |
|---|---|---|---|---|---|
| 1. 3D layout | Sales, concept reviews, the "vibe" loop itself | Medium (good at structure, weak at geometry) | S–M, ~1–2 weeks | Low | **Built (v0.2)** |
| 2. PLC control logic | Automation engineers | Good for skeletons, weak for motion/safety | M for a skeleton, L to simulate | Medium–high | Build a skeleton after 4 |
| 3. CAD export (STEP) | Mechanical design office | Poor without a template library | L–XL, 1–2+ months | High | Only with a parts/template library |
| 4. Specs + safety documents | Pre-sales, project managers, validation (GMP) | Excellent (it is text) | S–M, ~1 week | Medium (compliance wording) | **Built (v0.2)** |

\* One developer, rough order of magnitude, on top of v0.1.

---

## 1. Interactive 3D layout

A simplified 3D model in the browser (three.js / react-three-fiber): one block per station along
the product flow, conveyors between them, guards and cabinet around them. It updates on every
revision, and clicking a station shows its components.

**Pros**
- Makes the prompting loop tangible: you "see" the machine change after each prompt. This is
  what makes the tool feel like *vibe coding a machine* rather than filling a form.
- Catches design errors early (a station missing from the flow, a footprint that can't fit).
- Very useful in sales and concept reviews with customers.
- Cheap and low risk: it only reads the model; no engineering liability.
- A 2D top-view (SVG) variant is even cheaper and can come first.

**Cons**
- Schematic only: boxes and envelopes, not engineering geometry.
- LLMs are unreliable at spatial coordinates. The layout must be computed by our code from station
  order and envelope sizes; the AI should only propose dimensions. That needs a small layout
  engine (flow line, U-shape, rotary).
- Risk that people read a nice-looking picture as a validated design. It needs a clear
  "concept" label.

**What it needs in the model:** an envelope per station (length × width × height), a layout style,
and optionally a transport type between stations. That's a small schema extension.

## 2. PLC control logic (IEC 61131-3)

Generate a Structured Text project skeleton from the design: one function block per station with a
state machine (ideally the PackML / ISA-TR88 state model used in packaging), an I/O list derived
from sensors and actuators in the BOM, alarms, and a machine-level mode manager. Export as plain
`.st` files and PLCopen XML.

**Pros**
- High value for automation engineers, who start every project with the same skeleton.
- Code is text, which suits LLMs. The structure (states, I/O, alarms) is very regular.
- The **I/O list** is deterministic (count sensors, valves, drives in the BOM) and useful on its
  own: it sizes the PLC I/O and the cabinet, and it feeds the spare-parts catalog.
- PLCopen XML imports into CODESYS-based platforms (Beckhoff TwinCAT, Schneider, B&R and others).

**Cons**
- Vendor dialects differ: Siemens TIA (SCL) and Rockwell (mostly ladder) need their own export.
- Motion (electronic cams, gearing, registration) is where the real complexity is, and generated
  motion code needs heavy review.
- **Safety logic must never be generated for use.** Safety functions need a qualified engineer,
  a safety PLC or relay, and validation to ISO 13849 / IEC 62061. The tool can only list the
  required safety functions.
- Hard to verify without a simulator. A soft-PLC test harness (CODESYS Control Win, OpenPLC) is
  extra work but turns it from "text" into "tested skeleton".
- Liability: generated control code running real actuators is dangerous if trusted blindly.

## 3. CAD export (STEP)

Generate parametric 3D geometry with CadQuery / build123d (Python, OpenCascade) and export STEP
for SolidWorks, Creo or Inventor: frame, base plates, guards, conveyors, and placeholders for
commercial parts.

**Pros**
- A tangible deliverable for the mechanical design office.
- STEP opens in every CAD system.
- Frames, guards and conveyors are very parametric, so templates work well for them.
- Supplier CAD models (Festo, SMC, igus, SICK…) exist and could be dropped in. Platforms such as
  CADENAS PARTcommunity and TraceParts distribute them, but need a commercial agreement for
  automated access.

**Cons**
- The heaviest option by far. Useful output needs a **library of parametric templates designed by
  mechanical engineers**. The LLM cannot do real mechanical design: tolerances, stiffness,
  kinematics, cam profiles, format parts.
- Without that library the output is only envelope geometry, close to what option 1 shows for
  much less effort.
- OpenCascade is a large dependency (hundreds of MB) and fiddly on Windows.
- Risk that a generated model is taken for a design; every part still needs a designer.

## 4. Specifications and safety documents

Generate, per revision: a functional description, sequence of operations, I/O list, utilities and
consumption, spare-parts list, and, for regulated customers, document skeletons (URS → FS/DS for
GAMP 5 pharma projects, FAT/SAT checklists). Also a **hazard checklist** organised along
ISO 12100, plus the safety functions the machine likely needs. Export to DOCX/PDF/Markdown.

**Pros**
- This is where LLMs are strongest. Quality is high and it is quick to build.
- Immediate business value: offers, kick-off meetings and validation packages all start from
  these documents.
- Timely: the EU Machinery Regulation (EU) 2023/1230 applies from **20 January 2027** and replaces
  the Machinery Directive. Teams will be updating their technical-file templates anyway.
- Every document derives from the same model, so it stays consistent with the BOM.

**Cons**
- Compliance wording is risky. A generated text must never claim conformity or *be* the risk
  assessment. It is a draft checklist that a qualified person completes and signs.
- Standards are copyrighted: we can cite clause numbers, not reproduce text.
- Company templates vary. We'd want to import the company's own DOCX templates.

---

## How v0.2 implements options 1 and 4

- **3D layout** (`services/layout.py`, `components/Layout3D.tsx`). The AI proposes an envelope per
  station (length × width × height) and `layout_style` (`inline` or `u_shape`). Code computes the
  positions: flow stations in sequence, cabinets and utilities behind the line, a guard enclosure
  and base frame from the safety and frame stations. Stations without envelopes get defaults per
  kind. Rendered with three.js; clicking a station shows its components.
- **Documents** (`services/documents.py`, `components/DocumentsView.tsx`). Built by rules from the
  design, not written by the AI: overview, functional description, sequence of operations with a
  cycle-time vs throughput check, estimated I/O list (e.g. a cylinder = 1 valve output + 2
  end-position inputs) with PLC sizing, recommended spares, a hazard checklist along ISO 12100
  hazard groups, and the safety functions to specify, with "PL to be determined". Export to
  .docx, .md, or print/PDF. They work in demo mode too.

## Recommendation

1. **3D layout + specs/documents first** (done in v0.2). They are cheap and low risk, and together they make the
   loop feel real (you see the machine and read its description after every prompt).
2. **Then the I/O list and a PLC skeleton** (PackML state machine per station, PLCopen XML),
   explicitly without safety logic.
3. **CAD only if** the mechanical team will help build a template library. Without one, it isn't
   worth the effort.

### How to choose
- Users are **sales / pre-sales**: 3D layout + documents.
- Users are **automation engineers**: I/O list + PLC skeleton.
- Users are the **mechanical design office**: CAD, and plan for the template library.
- **Demo or investor pitch**: the 3D layout is the most convincing.
