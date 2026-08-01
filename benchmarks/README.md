# Performance benchmark results

These are engineering measurements, not demographic evidence. They were run
on 1 August 2026 under WSL2 Linux on an Intel Core Ultra 7 155H (22 logical
CPUs), Python 3.12.3, PostgreSQL 15, and a host with 7.4 GiB RAM. All comparison
runs use `ni_current_community`, seed 42, and the same generated PostgreSQL
baseline. Absolute timings depend on hardware and database state.

Reproduce a run with:

```bash
venv/bin/python scripts/benchmark_simulation.py \
  --database-url "$DATABASE_URL" \
  --engine columnar --expected-size 25000 \
  --start-year 2025 --end-year 2025 --seed 42 \
  --enforce-budget --output benchmark.json
```

The JSON report records every sample and reports total, median, and p95 CPU and
wall time per stage, SQL statements visible to SQLAlchemy, affected rows, peak
RSS, SSE bytes, inputs, and results. Arrow/ADBC baseline loading is one direct
columnar PostgreSQL query and therefore does not appear in SQLAlchemy's event
counters.

## Budget results

Core-year time is births + deaths + external migration + relocation. Snapshot,
event, and checkpoint persistence are measured separately so storage costs
cannot be hidden inside the simulation figure.

| Population | ORM core year | Columnar core year | Budget | Result |
|---:|---:|---:|---:|---|
| 25,000 | 2.645 s | 0.150 s p95 | 0.250 s | pass |
| 250,000 | 29.63 s | 0.292 s p95 | 0.750 s | pass |
| 1,903,175 | not practical for rollout | 1.962 s p95 | 3.000 s | pass |

The CI gate seeds 25,000 people and fails when the columnar core year exceeds
250 ms. The same benchmark command supports the 250K and full-scale gates on a
suitably provisioned runner.

## Engine parity

The engines deliberately use different deterministic selection mechanisms, so
selected UUIDs need not match. Totals and distributions are compared within
statistical tolerances. Both engines are deterministic for their own fixed
inputs and seed.

| 250K component | ORM | Columnar | Difference |
|---|---:|---:|---:|
| Births | 2,468 | 2,468 | 0.00% |
| Deaths | 2,204 | 2,225 | 0.95% |
| Immigration | 3,103 | 3,108 | 0.16% |
| Emigration | 2,864 | 2,905 | 1.43% |
| Relocations | 4,943 | 4,954 | 0.22% |
| Net change | +503 | +446 | 57 people, or 0.023% of baseline |

The automated parity harness also compares total population, every community
background and LGD cohort, event components, and NI/LGD political estimates.
Historical, current-flat, and community-differentiated model determinism remain
covered by the model and simulation suites. The ORM implementation is retained
for one release as a diagnostic benchmark path; production execution uses the
columnar worker.

## Full population through 2050

A clean 26-year run from 2025 through 2050 used all 1,903,175 baseline people.
It ended at 1,906,726 people. Repeating the run produced identical annual event
counts and totals.

| Measurement | Result |
|---|---:|
| Total wall time, including persistence | 119.07 s |
| Core-year p95 | 1.962 s |
| Peak worker RSS | 986,324 KiB |
| Median event persistence per year | 2.499 s |
| p95 event persistence per year | 3.672 s |
| Median snapshot and polling aggregation | 0.251 s |
| p95 snapshot and polling aggregation | 0.319 s |
| Mean aggregate SSE payload | 22,474 bytes/year |
| Total SSE payload | 584,324 bytes |

A separate cold one-year full-scale run measured 7.756 seconds end to end:
2.804 seconds was baseline loading, 0.042 seconds run preparation, and 4.409
seconds was simulation, aggregate calculation, all persistence, final
checkpoint, and other post-load work. This meets the under-five-second first
stream target when the explicitly excluded cold load is removed. Its peak RSS
was 985,012 KiB.

Annual population rose initially and then declined to the stated 2050 result.
The model's direction is consistent with the NISRA 2024-based principal
projection, although its turning point and levels are not an exact reproduction
because the synthetic baseline and community differentials are estimates. In
particular, current-model mortality is not yet age-specific; this is a model
quality limitation rather than a performance shortcut.

Both LucidTalk and NILT calibrations were checked at 2025, 2037, and 2050 for NI
and all LGDs. Derry and Strabane remained materially more pro-unity than NI
overall (LucidTalk unite shares 66.2% versus 46.3% in 2025, and 62.4% versus
47.6% in 2050). Polling values are estimates from each year's simulated joint
location/community/age counts, not measured local voting intention. Those
compact counts are retained privately with each snapshot so future custom
polling baselines can be calculated on demand without scanning individuals.

## Storage and query plans

The 26-year full run wrote 3,200,342 append-only individual events. Their row
data occupied 560 MB; its final checkpoint occupied 35 MB; 26 compressed JSON
snapshots occupied 166 KiB. On the shared benchmark table, the heap was 1,253
MB and indexes 978 MB for 6,926,328 events, giving an approximate complete
per-run footprint of 1.05 GB when proportional index storage is included.
Retention and per-run checkpoint limits therefore remain essential for public
hosting.

Indexes were selected with `EXPLAIN (ANALYZE, BUFFERS)` on the full data:

- Annual event pagination uses `(run_id, year, id)` and returns 100 events in
  0.53 ms. Before adding `id` to this access path it scanned 6.68 million rows
  via the primary key and took 2.31 seconds.
- Individual history uses `(run_id, person_id, year)` and returned a known
  person's events in 3.15 ms.
- Checkpoint lookup uses `(run_id, year)` and measured 0.04 ms.

## Dominant costs and limitations

At full scale the dominant recurring costs are event persistence, internal
relocation, and external migration. Serialization is approximately 0.15 ms and
is immaterial. The browser receives only aggregate snapshots; individual state
is available through paginated history APIs and downloadable Parquet
checkpoints.

Measurements include PostgreSQL and checkpoint writes. They do not claim that
all public hosting environments will match this workstation, nor that generated
demographics or political estimates are observed facts. Published source data,
transformations, and model-specific limitations remain documented beside the
model inputs.
