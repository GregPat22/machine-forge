# ADR 0032: Unused axes have idle statistics

Date: 2026-10-30. Status: accepted. Extends ADR 0027; review finding R11.

Timing statistics were built only from motion bars, so an unused mechanism disappeared from the
result. The options were to keep that omission or report all mechanisms as the phase spec says.
Greg authorized the technically sound timing fix after reviewing the proposed test change.

A computable station reports unused mechanisms with busy time 0, idle time equal to the cycle
and utilisation 0. Their unused motion inputs need not be known. They have no diagram bar;
existing moving-axis statistics retain their order, followed by unused axes in model order.
Engine version 3 replaces older cached results. Not-computable stations still have no statistics.
