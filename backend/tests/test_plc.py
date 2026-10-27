from __future__ import annotations

import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

import pytest

from app.llm.mock import demo_design
from app.models import MachineDesign
from app.services.plc import generate, identifier, to_plcopen_xml, to_zip

NS = {"p": "http://www.plcopen.org/xml/tc6_0201"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def test_identifiers_are_valid_iec_names() -> None:
    assert identifier("Film unwind & forming", "FB_S01_") == "FB_S01_FilmUnwindForming"
    project = generate(demo_design("blister"), 1)
    gvl = next(f for f in project.files if f.name == "GVL_IO.st").content
    names = re.findall(r"^\s{4}(\w+) : (?:BOOL|INT);", gvl, re.M)
    assert names and all(IDENT.match(n) and "__" not in n for n in names)


def test_station_blocks_and_sequences() -> None:
    project = generate(demo_design("blister"), 2)
    names = [f.name for f in project.files]
    assert names[:4] == ["E_PackMLState.st", "E_PackMLCmd.st", "GVL_IO.st", "FB_PackML.st"]
    assert "PRG_Main.st" in names and len([n for n in names if n.startswith("FB_S")]) == 5
    forming = next(f.content for f in project.files if f.name.startswith("FB_S01"))
    assert "S01_forming_cyl_DO1 := TRUE;" in forming and "IF S01_forming_cyl_DI2 THEN" in forming
    assert "TODO move the axis" in forming
    main = next(f.content for f in project.files if f.name == "PRG_Main.st")
    assert "fbS02(eCmd := eCmd, bAbortAll := bAnyFault, bCycleTrigger := fbS01.bCycleDone);" in main
    assert "NOT implemented" in main and "Safe Torque Off" in main
    assert project.io_counts["Axis"] == 2 and project.axes


def test_case_labels_are_unique_per_station() -> None:
    for f in generate(demo_design("blister"), 1).files:
        if f.name.startswith("FB_S"):
            labels = re.findall(r"^\s{8}(\d+):", f.content, re.M)
            assert len(labels) == len(set(labels)), f.name


def test_plcopen_xml_structure() -> None:
    design = demo_design("blister")
    root = ET.fromstring(to_plcopen_xml(design, design.name))
    pous = root.findall(".//p:pou", NS)
    assert {p.get("name") for p in pous} >= {"FB_PackML", "PRG_Main"}
    assert root.find(".//p:dataType[@name='E_PackMLState']", NS) is not None
    assert root.find(".//p:task/p:pouInstance[@typeName='PRG_Main']", NS) is not None
    assert len(root.findall(".//p:globalVars/p:variable", NS)) > 10


@pytest.mark.skipif(not os.environ.get("MF_PLCOPEN_XSD"), reason="set MF_PLCOPEN_XSD to the tc6_xml_v201.xsd path")
def test_plcopen_xml_validates_against_tc6_schema() -> None:
    from lxml import etree

    schema = etree.XMLSchema(etree.parse(os.environ["MF_PLCOPEN_XSD"]))
    design = demo_design("blister")
    assert schema.validate(etree.fromstring(to_plcopen_xml(design, design.name).encode()))


def test_zip_contains_st_files_xml_and_readme() -> None:
    design = demo_design("blister")
    data = to_zip(generate(design, 1), design)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "plcopen.xml" in names and "README.txt" in names and "st/PRG_Main.st" in names


def test_empty_design_still_generates() -> None:
    project = generate(MachineDesign(name="t", machine_type="t", summary="t"), 1)
    assert any("no flow stations" in w for w in project.warnings)
    ET.fromstring(to_plcopen_xml(MachineDesign(name="t", machine_type="t", summary="t"), "t"))
