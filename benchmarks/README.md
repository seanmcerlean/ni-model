# Performance benchmark results

Benchmark results are engineering measurements, not demographic evidence. Run
`scripts/benchmark_simulation.py` against PostgreSQL and retain the generated
JSON when comparing engine implementations.

## ORM baseline: 25,000 people

Measured 31 July 2026 under WSL2 using Python 3.12 and PostgreSQL 15. Model:
`ni_current_community`, year 2025, seed 42.

| Stage | Wall time | SQL statements |
|---|---:|---:|
| Clone immutable baseline into run | 2.258 s | 31 |
| External migration | 0.736 s | 8 |
| Internal relocation | 0.585 s | 11 |
| Age every resident | 0.547 s | 1 |
| Births | 0.373 s | 4 |
| Deaths | 0.358 s | 4 |
| Flush individual mutations | 0.211 s | 3 |
| Aggregate snapshot and both polls | 0.099 s | 2 |
| Persist snapshot | 0.021 s | 3 |
| Serialize 21,858-byte SSE snapshot | <0.001 s | 0 |

Peak process RSS was 111,996 KiB. The simulated population changed from 25,000
to 25,054. The dominant costs show that payload serialization is immaterial;
baseline cloning, repeated ORM cohort materialisation, and population-wide row
updates must be removed. The current engine is far outside the plan's 250 ms
25K yearly target even when baseline cloning is excluded.

Re-run before and after each engine tranche. Hardware and database state affect
absolute timings, so comparisons must use the same host, baseline, model, year,
and seed.
