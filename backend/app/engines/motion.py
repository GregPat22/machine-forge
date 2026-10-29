"""Motion profiles for one rest-to-rest move of one axis (Phase 2, section B).

Pure functions over numbers: no I/O, no model imports. Units pass through unchanged: mm, mm/s,
mm/s², mm/s³ for a linear axis, the same in degrees for a rotary axis; times are in seconds. Moves
start and end at rest and decelerate as hard as they accelerate (symmetric limits). Zero, negative,
NaN or infinite inputs raise `MotionError`; nothing is clamped or approximated.

Source: L. Biagiotti, C. Melchiorri, *Trajectory Planning for Automatic Machines and Robots*,
Springer, 2008, ISBN 978-3-540-85628-3, chapter 3. Section titles and first pages as printed in
the book's table of contents (p. X), read on 2026-10-29 from the publisher's table of contents
hosted by beck-shop.de:
https://beckassets.blob.core.windows.net/product/toc/242170/9783540856283_toc_001.pdf
  - 3.2   "Linear Trajectory with Parabolic Blends (Trapezoidal)", p. 62
  - 3.2.2 "Trajectory with preassigned acceleration and velocity", p. 65
  - 3.2.5 "Displacement time of a trapezoidal trajectory", p. 69
  - 3.4   "Trajectory with Double S Velocity Profile", p. 79
  - 3.4.3 "Double S with null initial and final velocities", p. 90
  - 3.4.5 "Displacement time of a double S trajectory", p. 101
TODO(source): the page and equation number of each formula inside these sections were not checked
against the text of the book, only the table of contents.

Cross-check for the jerk-limited profile: P. Lambrechts, M. Boerlage, M. Steinbuch, "Trajectory
planning and feedforward design for electromechanical motion systems", Control Engineering
Practice 13 (2005), no. 2, pp. 145-157. TODO(source): section and page of its third-order profile
not checked against the text.

Notation follows the book: Tj jerk time, Ta acceleration time, Tv constant-speed time, Td
deceleration time (= Ta here), T = Ta + Tv + Td.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class MotionError(ValueError):
    """An input the motion engine cannot use: zero, negative, NaN, infinite or not a number."""


@dataclass(frozen=True)
class MoveProfile:
    """One rest-to-rest move. Phase times in seconds; distance, speed and acceleration in the axis unit.

    `jerk_s` is the time of each constant-jerk ramp inside the acceleration and the deceleration
    phase (0 for a trapezoidal profile). `accel_s` and `decel_s` include those ramps.
    """

    distance: float
    duration_s: float
    peak_speed: float
    peak_acceleration: float
    jerk_s: float
    accel_s: float
    cruise_s: float
    decel_s: float

    def sample(self, n: int) -> list[tuple[float, float, float]]:
        """`n` evenly spaced points `(t, position, speed)` from 0 to `duration_s`, both included."""
        if isinstance(n, bool) or not isinstance(n, int) or n < 2:
            raise MotionError(f"sample needs an integer n >= 2, got {n!r}")
        times = [self.duration_s * i / (n - 1) for i in range(n - 1)] + [self.duration_s]
        return [(t, *self._state(t)) for t in times]

    def _state(self, t: float) -> tuple[float, float]:
        """Position and speed at time t. The deceleration mirrors the acceleration (symmetric move)."""
        if t <= self.accel_s:
            return self._accelerating(t)
        if t < self.accel_s + self.cruise_s:
            return self.peak_speed * (self.accel_s / 2 + t - self.accel_s), self.peak_speed
        q, v = self._accelerating(self.duration_s - t)
        return self.distance - q, v

    def _accelerating(self, t: float) -> tuple[float, float]:
        """Position and speed at time t in [0, Ta]. The acceleration phase is point-symmetric about
        its midpoint, v(Ta - t) = v_peak - v(t), so its second half is computed from its first."""
        if t <= self.accel_s / 2:
            return self._ramp_up(t)
        tau = self.accel_s - t
        q, v = self._ramp_up(tau)
        return self.peak_speed * (self.accel_s / 2 - tau) + q, self.peak_speed - v

    def _ramp_up(self, t: float) -> tuple[float, float]:
        """First half of the acceleration phase: constant jerk for Tj, then constant acceleration."""
        a, tj = self.peak_acceleration, self.jerk_s
        if t < tj:
            j = a / tj
            return j * t**3 / 6, j * t * t / 2
        return a / 6 * (3 * t * t - 3 * tj * t + tj * tj), a * (t - tj / 2)


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MotionError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise MotionError(f"{name} must be finite and > 0, got {value!r}")
    return float(value)


def _profile(distance: float, peak_speed: float, peak_acceleration: float, jerk_s: float,
             accel_s: float, cruise_s: float) -> MoveProfile:
    profile = MoveProfile(
        distance=distance,
        duration_s=accel_s + cruise_s + accel_s,
        peak_speed=peak_speed,
        peak_acceleration=peak_acceleration,
        jerk_s=jerk_s,
        accel_s=accel_s,
        cruise_s=cruise_s,
        decel_s=accel_s,
    )
    if not all(math.isfinite(x) for x in (profile.duration_s, peak_speed, peak_acceleration, jerk_s)):
        raise MotionError("inputs are outside the floating-point range of the motion engine")
    return profile


def trapezoidal(distance: float, max_speed: float, acceleration: float) -> MoveProfile:
    """Rest-to-rest trapezoidal speed profile (linear trajectory with parabolic blends).

    Biagiotti & Melchiorri (2008), section 3.2 (p. 62), with preassigned acceleration and speed as
    in 3.2.2 (p. 65) and the displacement time of 3.2.5 (p. 69). TODO(source): equation numbers.

    With Ta = v/a: if the distance allows a constant-speed phase (s >= v²/a, that is
    Tv = s/v - v/a >= 0) then T = s/v + v/a. Otherwise the speed is never reached (triangular
    profile): Ta = √(s/a), T = 2·√(s/a), peak speed √(s·a).
    """
    s = _positive("distance", distance)
    v = _positive("max_speed", max_speed)
    a = _positive("acceleration", acceleration)
    cruise = s / v - v / a
    if cruise >= 0:
        return _profile(s, v, a, 0.0, v / a, cruise)
    return _profile(s, math.sqrt(s * a), a, 0.0, math.sqrt(s / a), 0.0)


def s_curve(distance: float, max_speed: float, acceleration: float, jerk: float) -> MoveProfile:
    """Rest-to-rest double-S (seven-segment, jerk-limited) speed profile with symmetric limits.

    Biagiotti & Melchiorri (2008), section 3.4 (p. 79), case of null initial and final speed in
    3.4.3 (p. 90); displacement time in 3.4.5 (p. 101). Cross-check: Lambrechts, Boerlage and
    Steinbuch (2005). TODO(source): equation numbers.

    First assume the maximum speed is reached:
      - if v·j >= a²: the acceleration limit is reached, Tj = a/j, Ta = Tj + v/a;
      - else: it is not, Tj = √(v/j), Ta = 2·Tj, peak acceleration j·Tj.
    Then Tv = s/v - Ta. If Tv >= 0 the speed is reached and T = 2·Ta + Tv. If Tv < 0 the speed is
    not reached, Tv = 0, and:
      - if s >= 2·a³/j²: the acceleration limit is reached, Tj = a/j, Ta = Tj/2 + √((Tj/2)² + s/a);
      - else: it is not, Tj = ∛(s/(2·j)), Ta = 2·Tj, peak acceleration j·Tj.
    The peak speed is then (peak acceleration)·(Ta - Tj), and T = 2·Ta.
    """
    s = _positive("distance", distance)
    v = _positive("max_speed", max_speed)
    a = _positive("acceleration", acceleration)
    j = _positive("jerk", jerk)
    if v * j >= a * a:
        tj, ta, a_peak = a / j, a / j + v / a, a
    else:
        tj = math.sqrt(v / j)
        ta, a_peak = 2 * tj, j * tj
    cruise = s / v - ta
    if cruise >= 0:
        return _profile(s, v, a_peak, tj, ta, cruise)
    if s >= 2 * a * a * a / (j * j):
        tj = a / j
        ta, a_peak = tj / 2 + math.sqrt(tj * tj / 4 + s / a), a
    else:
        tj = math.cbrt(s / (2 * j))
        ta, a_peak = 2 * tj, j * tj
    return _profile(s, a_peak * (ta - tj), a_peak, tj, ta, 0.0)
