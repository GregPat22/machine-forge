# Throughput trace format

The throughput engine (`backend/app/engines/throughput.py`, Phase 3) records how every product
moves through the line during a short window of the run. The trace is part of the stored
`ThroughputResult` of a revision (ADR 0003, ADR 0028). The Phase 4 viewer plays it on the 3D
model; it needs nothing else from the simulation to place every product at any time.

This document is the contract. The engine implements it and `backend/tests/test_trace.py` checks
the engine's trace against it, including both examples below. A change to this format, or to any
number in it, bumps the throughput engine version.

## Nodes

A product is always in one node of the line, or outside the line. The nodes are:

| kind        | id                | meaning                                                        |
| ----------- | ----------------- | -------------------------------------------------------------- |
| `source`    | null              | outside the line, before it: the unlimited supply              |
| `sink`      | null              | outside the line, after it: good output                        |
| `station`   | the station id    | a station of the line, including a reject station              |
| `transport` | the transport id  | a transport between two stations                               |

Every node carries its kind, because a station and a transport may share an id (ids are unique
per kind, `services/patch.py`) and a station may be called `source` or `sink`.

The node list is fixed by the design, not by the events: `source`, `sink`, then every station of
`MachineDesign.process_order()` in that order (every station of the graph, reject stations
included), then every
transport in the order of `MachineDesign.transports`. A node no product touched is still listed.

## Events

One event is one move of one product: `(t, piece, from, to)`.

- `t`: seconds of simulated time from the start of the window (below). Negative for the moves
  carried in from before the window.
- `piece`: an integer that names the product. Products are numbered 0, 1, 2, ... in the order
  they entered the line, counting only the products that appear in the trace. Products that
  entered at the same time are numbered by the position of their entry station in
  `process_order()`, then in the order that station took them.
- `from`, `to`: nodes. The product leaves `from` and is in `to` from time `t` on.

A move from a node to itself (`from` equal to `to`) marks a change inside the node: the product
reaches the end of a transport, or a station starts or ends the cycle that holds it. There are
exactly seven kinds of move; no other combination occurs.

| from          | to                         | meaning                                                                 |
| ------------- | -------------------------- | ----------------------------------------------------------------------- |
| `source`      | entry station S            | S takes a new product: the product enters the line                      |
| transport X   | station S (X's `to_station`) | S takes the product from the end of X                                 |
| station S     | S                          | first one after the product entered S: the cycle starts; second one: the cycle ends |
| station S     | transport X                | S passes the product on to X: it starts travelling on X                 |
| transport X   | X                          | the product reaches the end of X and waits there to be taken            |
| exit station S | `sink`                    | the product leaves the line as good output, when the cycle ends         |
| transport X   | station R (X's `reject_to`) | the product is rejected at the end of X and leaves the line, counted at R |

What each product does, in order, through a station S fed by transport X and passing on to
transport Y:

1. `X → S` S takes it (or `source → S` at an entry station).
2. `S → S` the cycle starts. When S handles several products per cycle, this comes when the
   last place is filled; until then the product waits in S.
3. `S → S` the cycle ends (breakdowns during the cycle make it later; they are not events).
4. `S → Y` S passes it on (or `S → sink` at an exit station). The time between 3 and 4 is the
   time the product waits in S for room downstream.
5. `Y → Y` it reaches the end of Y. The time between 4 and 5 is its travel on Y; it is the
   transport's travel time `T`, or longer when the product ahead reached the end later.
6. Then either the next station takes it (`Y → next station`, back to step 1), or it is
   rejected (`Y → reject station`, its last move). The time between 5 and 6 is waiting at the
   end of Y.

A rejected product's last move goes to its reject station. If a transport's `reject_to` is its
own `to_station`, a reject and a take look the same. Inside the window the second row of the table
below tells them apart: a move with time `< end_s` that is the product's last event is a reject. A
carried-out move (time `≥ end_s`) can stay ambiguous; no placement inside the window needs it.

## Where a product is at time t

For a time `t` with `0 ≤ t < end_s`, take the product's last event with time `≤ t` (in trace
order). The first row that matches gives its place:

| last event                       | place                                                                        |
| -------------------------------- | ---------------------------------------------------------------------------- |
| none (the product's first event is later than `t`) | not in the line yet                                        |
| the product's last event in the trace, with time `< end_s` | outside the line: it left to the `sink` or to a reject station |
| `A → X`, X a transport, A ≠ X    | on X, travelling: a fraction `(t − t1) / (t2 − t1)` of the way from its start to its end, where `t1` is this event's time and `t2` the time of the product's next event (`X → X`); at the end when `t2 = t1` |
| `X → X`, X a transport           | waiting at the end of X; products waiting there queue in the order they reached the end |
| `A → S`, S a station, A ≠ S      | in S, waiting for the cycle to start                                         |
| first `S → S` after entering S   | in S, cycle running                                                          |
| second `S → S` after entering S  | in S, cycle done, waiting to be passed on                                    |

The trace guarantees that each of these is decidable from the trace alone: every product in the
line at the start of the window has its move into its node carried in, and every product in the
line at the end has its next move carried out (see "Window"). So a product whose last event is
before `end_s` has left the line, and a product travelling on a transport always has the event
that tells when it reaches the end. How the viewer draws the motion between two events (uniform
speed, spacing of a queue) is the viewer's choice; the times are fixed here.

Not in the trace: station states without a product (starved, broken down). Those are in the
per-station shares of the result, not in the trace.

## Stored shape

The trace is one JSON object in the `ThroughputResult`:

```json
{
  "window_s": 60.0,
  "end_s": 60.0,
  "max_events": 20000,
  "time_decimals": 3,
  "nodes": [
    {"kind": "source", "id": null},
    {"kind": "sink", "id": null},
    {"kind": "station", "id": "st-a"},
    {"kind": "station", "id": "st-b"},
    {"kind": "transport", "id": "tr-x"}
  ],
  "events": [[0.0, 0, 0, 2], [0.0, 0, 2, 2], [2.0, 0, 2, 2], [2.0, 0, 2, 4]]
}
```

(Shortened to show the shape: the first four events of example 1 below. Not a complete trace.)

- `events`: arrays `[t, piece, from_index, to_index]`, the indices pointing into `nodes`.
- Times are rounded to `time_decimals` = 3 decimals (1 ms) with Python's `round(t, 3)`, taken on
  `t` already measured from the window start. A rounded `-0.0` is written as `0.0`. Every rule in
  this document (the window, carrying in and out, the cut, the sort) uses the rounded times.
- Events are sorted by `t`, then by `piece`. Events of one product with the same `t` keep the
  order in which they happened.
- `window_s`: the window length asked for. `end_s`: where the trace actually ends; less than
  `window_s` only when the trace was cut at the event cap. `max_events`: the cap.

## Window

- **Start** (`t = 0`): the moment the warm-up ends, which is also the start of the measured part
  of the run: the moment the `warmup_products`-th product leaves the line (500 by default;
  `ThroughputSettings`, spec Phase 3 section C.8). A product leaves the line by its move to `sink`
  or to a reject station; both count. With `warmup_products = 0`, the start of the run, with an
  empty line.
- **Length**: `trace_window_s` = **60 s** of simulated time. The window is `0 ≤ t < end_s`.
- **Cap**: `trace_max_events` = **20,000** events in the whole trace (about 0.5 MB as JSON).
- Both are engine constants, recorded in the result as `window_s` and `max_events`. They are
  fields of `ThroughputSettings` with these defaults so a test can ask for a short window; stored
  results always use the defaults.

A product is **in the line at time e** when its move from `source` has a time `< e` and its move to
`sink` or to a reject station has a time `≥ e` (or has not happened). For an end time `e`, the
trace holds:

1. **Carried in**: for every product in the line at 0, its last move into another node before 0
   (`from ≠ to`, time `< 0`) and the moves inside that node after it with time `< 0`. These
   events have negative times.
2. **Window**: every event with `0 ≤ t < e`.
3. **Carried out**: for every product in the line at `e`, its first event with time `≥ e`. One
   event per product, even when it has several at that time.

`end_s` is the largest `e` among `trace_window_s` and the distinct event times in
`[0, trace_window_s)` for which these three parts together have at most `trace_max_events` events.
Cutting at an event time keeps all events of that time out of the window: events at one time are
never split. If only `e = 0` fits, or none does, there is nothing to play: the trace has
`end_s = 0` and no events.

## Checks a trace passes

- Events are sorted as stated above; every index points into `nodes`; every move is one of the
  seven kinds.
- Each product's moves chain: each move starts in the node where its previous one ended.
- A product whose first event has a time `≥ 0` starts with a move from `source`. A product whose
  first event has a negative time was carried in, and starts with a move into its node.
- A product whose last event has a time `< end_s` ends with a move to `sink` or to a reject
  station. A product whose last event has a time `≥ end_s` was carried out, and has exactly one
  event at or after `end_s`.
- At most `max_events` events.

The simulation runs on past the measured products when it must, until the trace is complete:
every product in the line at the end of the window has made its next move. Only the measured
products count in the statistics; running on changes none of them.

## Example 1: three products, empty line

Settings: `warmup_products = 0`, `trace_window_s = 6.0`, the rest the defaults. A two-station
line, no rejects, no breakdowns, one product per cycle:

- `st-a`, entry station, cycle time 2.0 s.
- `tr-x`, belt from `st-a` to `st-b`, 100 mm long at 100 mm/s: travel time `T` = 1.0 s; capacity
  1 product.
- `st-b`, exit station, cycle time 2.5 s.

Worked by hand with the rules of spec Phase 3 section C (unlimited supply at the entry, outfeed
never blocked, blocking after service):

- 0.0: `st-a` takes product 0 and starts its cycle.
- 2.0: the cycle ends; `tr-x` is empty, so product 0 goes onto it. `st-a` takes product 1 and
  starts.
- 3.0: product 0 reaches the end of `tr-x`. `st-b` is idle: it takes it and starts.
- 4.0: product 1's cycle ends; `tr-x` is empty again (product 0 left it at 3.0), so product 1 goes
  onto it. `st-a` takes product 2 and starts.
- 5.0: product 1 reaches the end of `tr-x`. `st-b` is busy until 5.5: product 1 waits.
- 5.5: `st-b` ends product 0's cycle; product 0 leaves the line. `st-b` takes product 1 and
  starts.
- 6.0: product 2's cycle ends at `st-a` (carried out: the window ends at 6.0). Product 3 enters at
  6.0, so it is not in the line at the end and not in the trace.
- 8.0: product 1's cycle ends at `st-b` (carried out).

Product 0 left at 5.5, before the end: no event carried out.

```json
{
  "window_s": 6.0,
  "end_s": 6.0,
  "max_events": 20000,
  "time_decimals": 3,
  "nodes": [
    {"kind": "source", "id": null},
    {"kind": "sink", "id": null},
    {"kind": "station", "id": "st-a"},
    {"kind": "station", "id": "st-b"},
    {"kind": "transport", "id": "tr-x"}
  ],
  "events": [
    [0.0, 0, 0, 2], [0.0, 0, 2, 2],
    [2.0, 0, 2, 2], [2.0, 0, 2, 4], [2.0, 1, 0, 2], [2.0, 1, 2, 2],
    [3.0, 0, 4, 4], [3.0, 0, 4, 3], [3.0, 0, 3, 3],
    [4.0, 1, 2, 2], [4.0, 1, 2, 4], [4.0, 2, 0, 2], [4.0, 2, 2, 2],
    [5.0, 1, 4, 4],
    [5.5, 0, 3, 3], [5.5, 0, 3, 1], [5.5, 1, 4, 3], [5.5, 1, 3, 3],
    [6.0, 2, 2, 2],
    [8.0, 1, 3, 3]
  ]
}
```

Where the products are, read with the table above:

| t   | product 0                     | product 1                     | product 2                |
| --- | ----------------------------- | ----------------------------- | ------------------------ |
| 1.0 | `st-a`, cycle running         | not in the line yet           | not in the line yet      |
| 2.5 | on `tr-x`, half way           | `st-a`, cycle running         | not in the line yet      |
| 5.2 | `st-b`, cycle running         | waiting at the end of `tr-x`  | `st-a`, cycle running    |
| 5.8 | left the line                 | `st-b`, cycle running         | `st-a`, cycle running    |

## Example 2: the same line after a warm-up

The same line with `warmup_products = 1` and `trace_window_s = 1.0`. The run is the one of
example 1; the window starts when product 0 leaves the line, at 5.5 s of run time, so every time
below is the run time minus 5.5. Products 0 to 3 all appear in this trace, so they keep their
numbers from example 1.

- In the line at 0: products 0 (in `st-b`, its cycle ending at that instant), 1 (waiting at the end
  of `tr-x`) and 2 (in `st-a`). Carried in: product 0's move into `st-b` and its cycle start
  (3.0 → −2.5), product 1's move onto `tr-x` (4.0 → −1.5) and its arrival at the end
  (5.0 → −0.5), product 2's entry and cycle start (4.0 → −1.5).
- Window `[0, 1.0)`: at 0.0 product 0 ends its cycle and leaves, `st-b` takes product 1 and
  starts; at 0.5 product 2's cycle ends, it goes onto `tr-x` (empty since 0.0), `st-a` takes
  product 3 and starts.
- In the line at 1.0: products 1, 2 and 3. Carried out: product 2 reaches the end of `tr-x` at
  1.5, product 1's cycle ends at 2.5, product 3's cycle ends at 2.5.

```json
{
  "window_s": 1.0,
  "end_s": 1.0,
  "max_events": 20000,
  "time_decimals": 3,
  "nodes": [
    {"kind": "source", "id": null},
    {"kind": "sink", "id": null},
    {"kind": "station", "id": "st-a"},
    {"kind": "station", "id": "st-b"},
    {"kind": "transport", "id": "tr-x"}
  ],
  "events": [
    [-2.5, 0, 4, 3], [-2.5, 0, 3, 3],
    [-1.5, 1, 2, 4], [-1.5, 2, 0, 2], [-1.5, 2, 2, 2],
    [-0.5, 1, 4, 4],
    [0.0, 0, 3, 3], [0.0, 0, 3, 1], [0.0, 1, 4, 3], [0.0, 1, 3, 3],
    [0.5, 2, 2, 2], [0.5, 2, 2, 4], [0.5, 3, 0, 2], [0.5, 3, 2, 2],
    [1.5, 2, 4, 4],
    [2.5, 1, 3, 3], [2.5, 3, 2, 2]
  ]
}
```

Product 0's carried-in moves show why the move into the node is carried in too: without
`[-2.5, 0, 4, 3]`, the viewer could not tell whether `[-2.5, 0, 3, 3]` starts or ends a cycle.
