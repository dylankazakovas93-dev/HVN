# Session Contract

All boundaries are `America/New_York`. Source start is inclusive, source end is
exclusive, and the frozen profile is available immediately after source end.

| Family | Source start | Source end / freeze |
|---|---|---|
| Prior RTH | actual selected prior RTH date 09:30 | same date 16:00 |
| Full overnight | prior calendar date 18:00 | current date 09:30 |
| Midnight | current date 00:00 | current date 09:30 |
| Opening-hour RTH | current date 09:30 | current date 10:30 |

The generic constructor receives an explicit window. It does not infer a prior
trading day, holiday, early close, or roll. Those mechanics require an
authoritative calendar and MNQ contract source. Tests cover both DST transitions,
midnight crossing, and inclusive/exclusive source boundaries.

Only one-minute intervals with
`source_start <= bar_start_time < source_end` and
`bar_close_time <= freeze_time` contribute. Thus the 15:59–16:00 RTH bar is
included after completing at the freeze timestamp, while a 16:00–16:01 bar is
excluded. A bar starting at source end or later cannot mutate profile bins, POC,
nodes, boundaries, or rankings.
