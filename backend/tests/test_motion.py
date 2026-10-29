"""Motion engine: rest-to-rest trapezoidal and double-S (S-curve) profiles (Phase 2, section B).

Expected values are the closed forms of Biagiotti & Melchiorri (2008), sections 3.2 and 3.4,
worked out by hand in each test, never taken from running the engine.
"""

from __future__ import annotations

import math

import pytest

from app.engines.motion import MotionError, MoveProfile, s_curve, trapezoidal

TOL = 1e-9


def test_trapezoidal_time_matches_closed_form() -> None:
    # (distance, max_speed, acceleration), each with distance >= v²/a so the speed is reached.
    for s, v, a in [(200.0, 500.0, 2000.0), (720.0, 720.0, 1440.0), (2.0, 1.0, 1.0), (500.0, 50.0, 10.0)]:
        assert s > v * v / a, "test data: the speed must be reached"
        profile = trapezoidal(s, v, a)
        assert profile.duration_s == pytest.approx(s / v + v / a, abs=TOL)
        assert profile.peak_speed == pytest.approx(v, abs=TOL)
        assert profile.peak_acceleration == a
        assert profile.accel_s == pytest.approx(v / a, abs=TOL)
        assert profile.decel_s == pytest.approx(v / a, abs=TOL)
        assert profile.cruise_s == pytest.approx(s / v - v / a, abs=TOL)
        assert profile.jerk_s == 0.0


def test_triangular_case_when_max_speed_is_not_reached() -> None:
    s, v, a = 10.0, 500.0, 2000.0  # v²/a = 125 > 10
    profile = trapezoidal(s, v, a)
    assert profile.duration_s == pytest.approx(2 * math.sqrt(s / a), abs=TOL)
    assert profile.peak_speed == pytest.approx(math.sqrt(s * a), abs=TOL)
    assert profile.peak_speed < v
    assert profile.cruise_s == 0.0
    assert profile.accel_s == pytest.approx(math.sqrt(s / a), abs=TOL)


def test_trapezoidal_is_continuous_at_the_triangular_boundary() -> None:
    v, a = 400.0, 1600.0
    s = v * v / a  # 100: cruise phase of zero length
    at = trapezoidal(s, v, a).duration_s
    assert at == pytest.approx(s / v + v / a, abs=TOL)
    assert at == pytest.approx(2 * math.sqrt(s / a), abs=TOL)
    below = trapezoidal(s * (1 - 1e-12), v, a).duration_s
    above = trapezoidal(s * (1 + 1e-12), v, a).duration_s
    assert below == pytest.approx(at, abs=1e-9)
    assert above == pytest.approx(at, abs=1e-9)


def test_s_curve_cases_match_closed_form() -> None:
    """Section 3.4.3 (null initial and final speed), worked by hand. Tj = jerk time, Ta = acceleration
    time (= deceleration time), Tv = constant-speed time, T = 2·Ta + Tv."""
    # 1. Acceleration and speed reached: v·j = 1000 >= a² = 100, so Tj = a/j = 0.1,
    #    Ta = Tj + v/a = 1.1, Tv = s/v - Ta = 10 - 1.1 = 8.9, T = 2.2 + 8.9 = 11.1.
    p = s_curve(100.0, 10.0, 10.0, 100.0)
    assert (p.jerk_s, p.accel_s, p.cruise_s, p.decel_s) == pytest.approx((0.1, 1.1, 8.9, 1.1), abs=TOL)
    assert p.duration_s == pytest.approx(11.1, abs=TOL)
    assert (p.peak_speed, p.peak_acceleration) == pytest.approx((10.0, 10.0), abs=TOL)

    # 2. Speed reached, acceleration not: v·j = 25 < a² = 100, so Tj = √(v/j) = 0.2, Ta = 2·Tj = 0.4,
    #    Tv = 10/1 - 0.4 = 9.6, T = 10.4, peak acceleration j·Tj = 5.
    p = s_curve(10.0, 1.0, 10.0, 25.0)
    assert (p.jerk_s, p.accel_s, p.cruise_s, p.decel_s) == pytest.approx((0.2, 0.4, 9.6, 0.4), abs=TOL)
    assert p.duration_s == pytest.approx(10.4, abs=TOL)
    assert (p.peak_speed, p.peak_acceleration) == pytest.approx((1.0, 5.0), abs=TOL)

    # 3. Acceleration reached, speed not: Tv = 11/100 - 10.1 < 0; s = 11 >= 2a³/j² = 0.2, so
    #    Tj = a/j = 0.1, Ta = Tj/2 + √(Tj²/4 + s/a) = 0.05 + √1.1025 = 1.1, Tv = 0, T = 2.2,
    #    peak speed a·(Ta - Tj) = 10.
    p = s_curve(11.0, 100.0, 10.0, 100.0)
    assert (p.jerk_s, p.accel_s, p.cruise_s, p.decel_s) == pytest.approx((0.1, 1.1, 0.0, 1.1), abs=TOL)
    assert p.duration_s == pytest.approx(2.2, abs=TOL)
    assert (p.peak_speed, p.peak_acceleration) == pytest.approx((10.0, 10.0), abs=TOL)

    # 4. Neither reached: s = 2 < 2a³/j² = 2000, so Tj = ∛(s/(2j)) = ∛0.001 = 0.1, Ta = 2·Tj = 0.2,
    #    T = 0.4, peak acceleration j·Tj = 100, peak speed j·Tj² = 10.
    p = s_curve(2.0, 100.0, 1000.0, 1000.0)
    assert (p.jerk_s, p.accel_s, p.cruise_s, p.decel_s) == pytest.approx((0.1, 0.2, 0.0, 0.2), abs=TOL)
    assert p.duration_s == pytest.approx(0.4, abs=TOL)
    assert (p.peak_speed, p.peak_acceleration) == pytest.approx((10.0, 100.0), abs=TOL)


def test_s_curve_reduces_to_trapezoidal_as_jerk_grows() -> None:
    for s, v, a in [(200.0, 500.0, 2000.0), (10.0, 500.0, 2000.0)]:  # speed reached, then triangular
        reference = trapezoidal(s, v, a).duration_s
        gaps = [s_curve(s, v, a, j).duration_s - reference for j in (1e4, 1e6, 1e8, 1e12)]
        assert all(g >= 0 for g in gaps), "a jerk limit can only make the move longer"
        assert gaps == sorted(gaps, reverse=True) and gaps[0] > gaps[-1]
        assert gaps[-1] < 1e-6


def test_trapezoidal_matches_textbook_worked_example() -> None:
    """Biagiotti & Melchiorri (2008), section 3.2, Example 3.3, p. 67: three synchronized actuators
    with "vmax = 20 and amax = 20"; the largest displacement, actuator a, "q0,a = 0, q1,a = 50", sets
    the duration, printed "Ta = 1, T = 3.5". Read on 2026-10-29 as scanned text of pp. 66-67 in the
    Google Books preview (https://books.google.com/books?id=FiX1ceRT5zoC&pg=PA67, search "Ta = 1"
    and "Three synchronized"); subscripts are restored where the scan drops them.
    """
    p = trapezoidal(50.0, 20.0, 20.0)
    assert (p.accel_s, p.duration_s) == pytest.approx((1.0, 3.5), abs=TOL)


def test_s_curve_matches_textbook_worked_example() -> None:
    """Biagiotti & Melchiorri (2008), section 3.4.3, p. 93, the example of Fig. 3.19 (null initial
    and final speed, neither the maximum speed nor the maximum acceleration reached). Read on
    2026-10-29 as scanned text of p. 93 in the Google Books preview
    (https://books.google.com/books?id=FiX1ceRT5zoC&pg=PA93, search "computed in closed form"); the
    page image itself could not be opened. Printed, with the symbols the scan drops restored: "The
    boundary conditions are q0 = 0, q1 = 10, v0 = 0, v1 = 0, while the constraints are vmax = 10,
    amax = 20, jmax = 30. The resulting time intervals are Tj = 0.5503, Ta = 1.1006, Tv = 0."

    The book prints four decimals, so the tolerance is half a unit of the last one. The same
    sentence goes on "vlim = 8.6329 ... alim,a = 6.9641": these are not asserted, because they do
    not fit the printed times. With no cruise phase the distance is vlim·Ta (the speed profile is
    symmetric), and 8.6329 · 1.1006 = 9.50, not q1 - q0 = 10; the book's own p. 93 formula
    alim = jmax·Tj gives 30 · 0.5503 = 16.5, not 6.9641. P. 84 prints the same sentence, "Tj1 =
    0.2321, Tj2 = 0.2321 ... vlim = 8.6329 ... alim,a = 6.9641 and alim,d = -6.9641", for another
    example (30 · 0.2321 = 6.96), so p. 93 repeats it in error.
    """
    p = s_curve(10.0, 10.0, 20.0, 30.0)
    assert (p.jerk_s, p.accel_s, p.cruise_s, p.decel_s) == pytest.approx((0.5503, 1.1006, 0.0, 1.1006), abs=5e-5)


def test_rotary_axis_uses_degrees_unchanged() -> None:
    # A 90° index at 720 °/s and 7200 °/s² is the same arithmetic as 90 mm at 720 mm/s and 7200 mm/s².
    linear_mm = trapezoidal(90.0, 720.0, 7200.0)
    rotary_deg = trapezoidal(90.0, 720.0, 7200.0)
    assert rotary_deg == linear_mm
    assert rotary_deg.duration_s == pytest.approx(90 / 720 + 720 / 7200, abs=TOL)
    assert s_curve(90.0, 720.0, 7200.0, 72000.0) == s_curve(90.0, 720.0, 7200.0, 72000.0)


_PROFILES = [
    ("trapezoidal", lambda: trapezoidal(200.0, 500.0, 2000.0), 500.0),
    ("triangular", lambda: trapezoidal(10.0, 500.0, 2000.0), 500.0),
    ("s_curve a and v reached", lambda: s_curve(100.0, 10.0, 10.0, 100.0), 10.0),
    ("s_curve a not reached", lambda: s_curve(10.0, 1.0, 10.0, 25.0), 1.0),
    ("s_curve v not reached", lambda: s_curve(11.0, 100.0, 10.0, 100.0), 100.0),
    ("s_curve neither reached", lambda: s_curve(2.0, 100.0, 1000.0, 1000.0), 100.0),
]


@pytest.mark.parametrize(("label", "make", "max_speed"), _PROFILES, ids=[p[0] for p in _PROFILES])
def test_samples_start_and_end_at_rest_and_cover_the_distance(label: str, make, max_speed: float) -> None:
    profile: MoveProfile = make()
    samples = profile.sample(201)
    assert len(samples) == 201
    times = [t for t, _, _ in samples]
    assert times[0] == 0.0 and times[-1] == profile.duration_s
    steps = [b - a for a, b in zip(times, times[1:])]
    assert max(steps) - min(steps) < 1e-12, "points are evenly spaced"
    (_, q0, v0), (_, q1, v1) = samples[0], samples[-1]
    assert (q0, v0) == (0.0, 0.0)
    assert q1 == pytest.approx(profile.distance, abs=1e-9)
    assert v1 == pytest.approx(0.0, abs=1e-9)
    positions = [q for _, q, _ in samples]
    assert positions == sorted(positions), "a rest-to-rest move never goes backwards"
    assert all(0.0 <= v <= max_speed for _, _, v in samples)
    assert max(v for _, _, v in samples) <= profile.peak_speed + 1e-9
    # The speed samples integrate (trapezoid rule) to the distance: position and speed agree.
    dt = steps[0]
    area = sum((a[2] + b[2]) / 2 * dt for a, b in zip(samples, samples[1:]))
    assert area == pytest.approx(profile.distance, rel=1e-3)


def test_sample_needs_at_least_two_points() -> None:
    with pytest.raises(MotionError):
        trapezoidal(1.0, 1.0, 1.0).sample(1)


_BAD = [0.0, -1.0, math.nan, math.inf, -math.inf]


@pytest.mark.parametrize("bad", _BAD, ids=["zero", "negative", "nan", "inf", "-inf"])
def test_invalid_inputs_raise(bad: float) -> None:
    good = (200.0, 500.0, 2000.0, 1e5)
    for position in range(3):
        args = list(good[:3])
        args[position] = bad
        with pytest.raises(MotionError):
            trapezoidal(*args)
    for position in range(4):
        args = list(good)
        args[position] = bad
        with pytest.raises(MotionError):
            s_curve(*args)


def test_profiles_are_deterministic() -> None:
    cases = [lambda: trapezoidal(200.0, 500.0, 2000.0), lambda: trapezoidal(10.0, 500.0, 2000.0),
             lambda: s_curve(100.0, 10.0, 10.0, 100.0), lambda: s_curve(2.0, 100.0, 1000.0, 1000.0)]
    for make in cases:
        first, second = make(), make()
        assert first == second
        assert first.sample(50) == second.sample(50)
