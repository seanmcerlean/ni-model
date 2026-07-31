# Individual-population performance plan

## Objective

Simulate and retain Northern Ireland's complete individual population while
making yearly execution fast enough for interactive use. Every synthetic
resident must keep a stable identity and an inspectable history. Existing model
selection, adjustments, reproducible randomness, LGD detail, polling estimates,
durable runs, playback, and exports must remain available.

The target architecture keeps PostgreSQL as the authoritative database and uses
Polars/Apache Arrow in a worker process for vectorised simulation. PostgreSQL
stores the immutable population, run metadata, individual events, checkpoints,
and aggregate snapshots. The worker loads compact typed columns, applies a year
without Python ORM objects, persists events and snapshots, and emits progress to
the existing API stream.

## Performance budgets

Benchmarks must report median and 95th percentile timings on PostgreSQL for a
fixed seed and model.

| Workload | Target |
|---|---:|
| 25,000-person year | under 250 ms |
| 250,000-person year | under 750 ms |
| 1,903,175-person year | under 3 seconds |
| First streamed year, excluding a cold full-scale load | under 5 seconds |
| Full-scale worker memory per active run | under 1 GB |
| Repeated run with same model, inputs and seed | identical results |

Performance work is not complete if it meets timing targets by omitting
individual history, area detail, either polling calibration, or durable yearly
snapshots.

## Milestone 1: measurement and correctness harness

- Add a benchmark command for 25K, 250K, and full-scale baselines.
- Time baseline preparation, ageing, births, deaths, external migration,
  relocation, political calculation, snapshot aggregation, persistence, and
  serialization separately.
- Count SQL statements and rows transferred for every stage.
- Record CPU time, wall time, peak resident memory, and output size.
- Create deterministic reference runs for the flat current, differentiated
  current, and historical models.
- Add statistical parity assertions for totals, cohort distributions, LGDs,
  event counts, and political estimates.

Exit criteria: a reproducible report identifies the three dominant costs and
fails CI when the 25K benchmark regresses materially.

## Milestone 2: remove redundant database work

- Replace per-LGD snapshot queries with grouped queries over location,
  community background, age, gender, and origin.
- Derive NI totals from the same grouped result.
- Calculate LucidTalk and NILT, including all LGDs, from one shared
  location/background/age dataset.
- Cache immutable model configuration and compiled active rules by year.
- Avoid recounting the run population while creating the same yearly snapshot.
- Keep the SSE response schema unchanged.

Exit criteria: yearly snapshot and political output require no more than five
aggregate queries and exactly match the reference output.

## Milestone 3: compact individual representation

- Add stable `BIGINT` internal person identifiers while retaining UUID run IDs.
- Store `birth_year` instead of incrementing every resident's age annually.
- Use compact categorical codes in the worker for community background, gender,
  LGD, origin, and education.
- Add lifecycle fields for birth, death, arrival, and departure years.
- Add a location-history table with effective-from and effective-to years.
- Provide compatibility queries that expose age and current location exactly as
  the API expects.
- Select indexes from `EXPLAIN ANALYZE` evidence, with `run_id` leading all
  run-scoped access paths.

Exit criteria: any resident can be reconstructed at any simulated year, annual
ageing performs no population-wide database update, and existing API tests pass.

## Milestone 4: vectorised simulation worker

- Introduce a worker interface behind the existing model director contract.
- Load the active run into typed Polars/Arrow columns without constructing
  SQLAlchemy `Person` objects.
- Apply birth, death, immigration, emigration, and relocation rules using
  vectorised masks and bulk column operations.
- Give every event a deterministic random stream derived from run seed, year,
  event type, rule, and person identifier.
- Preserve sequential semantics: age, births, deaths, external migration,
  internal relocation, then snapshot.
- Support flat rules, community-differentiated rules, and all global and
  per-community run multipliers.
- Bulk-write new people and individual lifecycle/location events to PostgreSQL.

Exit criteria: the worker meets parity tolerances on reference runs, produces
identical output for repeated seeds, and meets the 25K and 250K budgets.

## Milestone 5: event history and checkpoints

- Keep the immutable starting population once rather than copying annual states.
- Persist individual births, deaths, arrivals, departures, and relocations as
  append-only events.
- Store aggregate JSON snapshots every year for immediate UI playback.
- Write a full individual Parquet checkpoint at a configurable interval and at
  run completion.
- Reconstruct arbitrary years from the nearest checkpoint plus subsequent
  events.
- Add an individual-history API with pagination and filters, without placing
  individual records in the normal yearly SSE payload.
- Verify restore, cancellation, replay, and deletion semantics.

Exit criteria: a user can inspect any individual or full population year,
restart an interrupted run from a checkpoint, and reproduce the same remaining
years.

## Milestone 6: background execution and concurrency

- Make simulation creation return a durable pending run immediately.
- Use a PostgreSQL-backed worker queue with `FOR UPDATE SKIP LOCKED`; avoid an
  additional queue service until measurements justify one.
- Stream status and completed snapshots independently of the worker transaction.
- Add cooperative cancellation between years.
- Limit concurrent workers by measured memory and database capacity.
- Ensure one slow full-scale run cannot block population and model endpoints.

Exit criteria: two simultaneous runs remain isolated, API health stays
responsive, cancellation is durable, and a worker restart does not corrupt or
duplicate events.

## Milestone 7: full-scale rollout

- Run the old and vectorised engines against the same seeded 25K and 250K
  populations and explain every difference.
- Run at least one complete 1,903,175-person current scenario through 2050.
- Validate yearly population components against the selected source model.
- Test area statistics and both polling calibrations at the first, middle, and
  final years.
- Make the vectorised worker the default only after correctness and performance
  gates pass.
- Retain the previous engine for one release as a diagnostic comparison path,
  then remove it after migration evidence is recorded.

Exit criteria: the full-scale target is met without reducing the feature set,
and the release documentation includes benchmark hardware, timings, memory,
limitations, and parity results.

## Explicit non-goals

- Do not replace individual residents with aggregate-only cohorts.
- Do not use Pandas object rows or Python loops as the main execution path.
- Do not send millions of residents through SSE; provide paginated individual
  access and downloadable checkpoints instead.
- Do not introduce Spark, GPU infrastructure, or a distributed database unless
  full-scale profiling demonstrates a need.
- Do not present speed improvements without PostgreSQL full-scale evidence.
