# Individual-population performance implementation

## Status

Implemented and verified for the 0.3.0 release. The application simulates the
complete 1,903,175-person synthetic population while retaining stable identity,
inspectable individual history, yearly NI/LGD aggregates, both polling models,
durable restart, and aggregate-only browser streaming.

PostgreSQL remains authoritative. A separate worker loads the immutable
baseline into compact Polars/Arrow columns, applies each year vectorially,
persists append-only lifecycle, relocation and community-transition events, writes yearly aggregate
snapshots, and creates periodic full-population Parquet checkpoints.

## Verified budgets

| Workload | Measured | Target |
|---|---:|---:|
| 25,000-person core year | 0.150 s p95 | under 0.250 s |
| 250,000-person core year | 0.292 s p95 | under 0.750 s |
| 1,903,175-person core year | 1.962 s p95 | under 3.000 s |
| First full-scale streamed year excluding cold load | 4.409 s | under 5.000 s |
| Full-scale peak worker RSS | 986,324 KiB | under 1 GiB |
| Repeated fixed-seed full run | identical annual results | identical |

Full methodology, hardware, parity tables, stage timings, payload sizes,
storage measurements, source validation, and limitations are recorded in
`benchmarks/README.md`.

## Implemented architecture

### Measurement and correctness

- `scripts/benchmark_simulation.py` benchmarks ORM and columnar engines on
  PostgreSQL, validates baseline size, and records wall/CPU total, median and
  p95 timing, SQL activity, RSS, outputs, and SSE size by stage.
- CI runs all backend and frontend gates plus a regression-failing 25K
  PostgreSQL benchmark.
- Deterministic tests cover historical, flat-current, and
  community-differentiated paths. Engine parity covers totals, events,
  community cohorts, and LGDs; polling recalculation is tested independently
  against the persisted joint aggregates.

### Aggregate boundary

- One grouped demographic query produces NI and every LGD snapshot.
- Yearly snapshots retain one private location/community/exact-age aggregate.
  LucidTalk, NILT, and custom LucidTalk-relative baselines are calculated on
  demand from it without storing person-level political scores, rerunning the
  simulation, or sending those private inputs over SSE.
- SSE messages contain only aggregate yearly data. They never contain resident
  rows or individual events.

### Compact individuals and deterministic evolution

- Residents have stable UUID identity and `BIGINT` person numbers. The worker
  stores `birth_year`, derives age for the requested year, and uses typed
  categorical columns for community, gender, LGD, origin, and education.
- Birth, death, arrival, departure, relocation, and community-transition events are append-only and
  include their effective year. This event log is the canonical lifecycle and
  location-history representation; separate mutable lifecycle columns and a
  duplicate location table were intentionally avoided.
- Random selection uses local deterministic streams derived from seed, year,
  event/rule identity, and stable resident identity. Process-global randomness
  is not used.
- Sequential semantics remain ageing-by-year, births, deaths, external
  migration, internal relocation, community transition, then aggregation.
- Flat rules, community-specific rules, and global/per-community multipliers
  all execute through the same production worker.

### History, checkpoints, and recovery

- The starting population is immutable and shared instead of cloned for each
  production run.
- Aggregate JSON snapshots are stored every year. Full Parquet checkpoints are
  stored at a configurable interval and at completion with size and SHA-256
  metadata.
- Arbitrary years reconstruct from the nearest checkpoint plus ordered events.
  Exact checkpoint years use lazy Parquet pagination.
- APIs expose filtered/paginated population years, individual histories, and
  downloadable exact-year Parquet checkpoints without widening SSE.
- Checkpoint resume, replay, cancellation, retention cleanup, and deletion are
  covered by regression tests.

### Public execution

- Run creation returns durable pending metadata immediately. A separate worker
  claims jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`.
- SSE polls durable snapshots independently of worker transactions. Cooperative
  cancellation occurs between years, and interrupted running jobs recover to
  pending before resuming from the latest checkpoint.
- Per-owner concurrency and horizon limits, worker count, timeout, retention,
  and checkpoint storage limits are configurable.
- `/health` is a constant-time application liveness probe and remains
  independent of simulation work. Two-run isolation and endpoint responsiveness
  are tested.
- Docker Compose and Kubernetes manifests run API and worker separately and
  share durable checkpoint storage.

## Full-scale verification

The release run evolved all 1,903,175 baseline residents from 2025 through 2050
and ended at 1,906,726. It retained yearly area details and both political
calibrations. The vector worker is now the production default; the ORM engine is
retained only as a one-release benchmark/diagnostic comparison path.

Full-scale `EXPLAIN ANALYZE` evidence selected run-leading indexes. Annual event
pagination now uses `(run_id, year, id)` and measured 0.53 ms for 100 rows;
individual history uses `(run_id, person_id, year)` and measured 3.15 ms.

## Operational limits and known model limitations

- A 26-year full run occupies approximately 1.05 GB after proportional event
  index storage, so a public deployment must enforce retention and storage
  quotas and monitor PostgreSQL growth.
- Current models preserve projected annual death totals while selecting deaths
  using NISRA 2024 age-specific mortality and the Census MS-B31 joint
  age/community baseline.
- Internal relocation and community differentials are documented estimates,
  not observed individual transitions.
- Polling projections are scenario estimates based on simulated adult
  location/community/age composition. They are neither area polls nor stored
  person-level constitutional preferences.
