"""A physical mechanism cannot execute two motions in the same parallel block."""
import pytest

from app.engines.timing import station_timing
from app.models import MachineDesign, Mechanism, Station, Step


def _station(groups, profile="trapezoidal"):
    return Station(id="st-test", name="Test", function="Test",
                   mechanisms=[Mechanism(id="m-axis", kind="linear", stroke=100, max_speed=100,
                                         acceleration=100, profile=profile, jerk=1000)],
                   steps=[Step(id=f"move-{i}", order=i + 1, kind="motion", mechanism_id="m-axis",
                               parallel_group=group) for i, group in enumerate(groups)])


@pytest.mark.parametrize("group", [0, 1, 7])
@pytest.mark.parametrize("profile", ["trapezoidal", "s_curve"])
def test_overlapping_motions_are_not_computable(group, profile):
    station = _station([group, group, group], profile)
    before = station.model_dump()
    result = station_timing(station)
    assert result.cycle_time_s is None
    assert [(r.code, r.mechanism_id, r.parallel_group) for r in result.not_computable] == [
        ("mechanism_overlap", "m-axis", group)]
    assert result.mechanisms == [] and result.diagram == []
    assert station.cycle_time_s is None
    assert station.model_dump() == before


@pytest.mark.parametrize("groups", [[None, None], [1, 2]])
def test_repeated_axis_in_sequential_blocks_is_computable(groups):
    result = station_timing(_station(groups))
    assert result.cycle_time_s == pytest.approx(4)
    assert result.mechanisms[0].busy_s == pytest.approx(4)
    assert result.mechanisms[0].idle_s == pytest.approx(0)
    assert result.mechanisms[0].utilisation == pytest.approx(1)


def test_editor_and_timing_api_handle_overlap_without_corrupting_the_design(client, storage):
    pid = storage.create_project("Synthetic test", "Initial reply",
                                 MachineDesign(name="Test", machine_type="test", summary="test"))
    station = _station([1, 1])
    response = client.post(f"/api/projects/{pid}/patches", json={
        "expected_revision": 1, "patches": [{"op": "add_station", "station": station.model_dump()}]})
    assert response.status_code == 200
    assert response.json()["design"]["stations"][0]["cycle_time_s"] is None
    result = client.get(f"/api/projects/{pid}/timing")
    assert result.status_code == 200
    assert result.json()["stations"][0]["not_computable"][0]["code"] == "mechanism_overlap"
    assert storage.get_project(pid).design.stations[0].model_dump() == station.model_dump()
