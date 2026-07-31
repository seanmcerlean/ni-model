# Project review

## Purpose

The project is an individual-level Northern Ireland cohort simulation. It stores
residents as database rows, applies demographic events sequentially, exposes
aggregated results through FastAPI, and animates the results in a React map.
Its political output is a configurable border-poll scenario derived from the
simulated population.

The useful scientific core is a cohort-component model:

1. age the resident population;
2. add births;
3. remove deaths;
4. apply external and internal migration;
5. persist and compare a year snapshot.

## Interpretation boundary

`religious_background` is used as a compact database name for **religion or
religion brought up in**, NISRA's census measure broadly consistent with
community background. Community background is relevant to political modelling,
but it is not a vote. A credible voting model must additionally be calibrated
against representative polling or election-study microdata, include turnout and
uncertainty, and be back-tested against outcomes it can actually observe.

## Evidence incorporated

- NISRA Census 2021 total population: 1,903,175.
- Community-background proxy (MS-B23): 869,753 Catholic; 827,545 Protestant and
  other Christian; 28,514 other religions; 177,360 none. Disclosure control
  makes this topic-table total three lower than the headline population.
- Census age structure: 365,200 aged 0–14, 1,211,400 aged 15–64, and 326,500
  aged 65+, with about 39,400 aged 85+.
- Country of birth (MS-A16): 1,646,276 Northern Ireland; 40,357 Republic of
  Ireland; 92,257 Great Britain; and 124,283 elsewhere.
- The official NISRA methodology ages cohorts annually before births, deaths,
  and migration adjustments.

Primary references:

- [NISRA Census 2021 religion tables](https://www.nisra.gov.uk/publications/census-2021-main-statistics-religion-tables)
- [NISRA guidance on religion outputs](https://www.nisra.gov.uk/system/files/statistics/census-2021-guidance-note-on-use-of-religion-question-outputs.pdf)
- [NISRA Census 2021 age and sex tables](https://www.nisra.gov.uk/publications/census-2021-main-statistics-demography-tables-age-and-sex)
- [NISRA 2024 mid-year estimates](https://datavis.nisra.gov.uk/population/2024-mid-year-estimates-for-northern-ireland.html)

## Material findings

### Corrected in the first improvement tranche

- The population now ages once per simulated year.
- Randomness is isolated per model run and seeded by configuration.
- Births require at least one female aged 15–49 in the configured cohort.
- Census 2021 community-background and age weights replace incompatible or
  implausible generated distributions.
- Invalid model configuration fails during loading.
- API model paths cannot escape the project `models/` directory.
- Synchronous year snapshots are captured in the year they represent instead of
  all being copied from the final population state.

### High-priority work ledger

- [x] **Durable, user-isolated runs.** Process-global result dictionaries were
  replaced by database-backed run IDs, run-scoped population rows, durable
  status, and persisted yearly snapshots. API and integration tests create two
  independent runs and reload their snapshots from PostgreSQL.
- [x] **Durable baseline and snapshot semantics.** Transaction savepoints were
  removed. Every run clones an immutable baseline, can restore that baseline,
  and retains aggregate snapshots across sessions. The initial Alembic
  migration exercises upgrade and downgrade against a clean PostgreSQL
  database.
- [ ] Ingest exact five-year age/sex, geography, country-of-birth, births,
  deaths, and migration series from NISRA rather than hand-maintained weights.
- [ ] Validate and update historic rates to the extent possible.
- [x] **Evidence-based internal relocation.** The model geography is now the 11
  current LGDs. All 110 directed LGD-to-LGD rates are derived from the public
  Census 2021 ODMG01 origin–destination table and exact source populations,
  with the pandemic-period and held-constant assumptions stated. Moves are
  selected from one pre-move population and applied simultaneously, preventing
  cascading or duplicate moves caused by rule order.
- [ ] Calibrate demographic rates and model uncertainty instead of applying undocumented fixed assumptions.
- [x] **Evidence-calibrated voting scenarios.** Voting output now excludes
  under-18s, projects turnout separately, calibrates stated preferences from
  the 1,199-adult NILT 2024 REFUNIFY results and published community-background
  and age cross-tabs, reports 95% survey intervals, and shows sensitivity to
  three allocations of undecided likely voters. It explicitly documents that
  resident adulthood is only an eligibility proxy and community background is
  not a vote.
- [x] **Current sourced model and frontend selection.** `ni_current.yaml` starts
  from the Census 2021 marginal baseline, uses observed NISRA components for
  2022–2024, and then the latest official 2024-based principal projection for
  2025–2074. Its normalized source series and reproducible extraction script
  are checked in. The models endpoint exposes the baseline, observation cutoff,
  projection version, and all derived rules; the frontend selector displays the
  model and those details.
- [x] **Full-scale database workflow.** Docker Compose now seeds and retains an
  exact-size 1,903,175-record Census 2021 PostgreSQL baseline and a separate
  1,536,065-record best-effort historical estimate in bounded batches. The
  historical profile is explicitly labelled as estimated: its total and legacy
  community-background assumptions are historical, while age, current-LGD,
  origin and education distributions reuse the current generator.
- [x] **Isolated run adjustments.** The frontend can apply bounded multipliers
  to birth, mortality, external-migration, and internal-relocation rules plus a
  reproducibility seed. Adjustments are validated by the API, stored with the
  durable run, and never modify the sourced YAML model.
- [ ] Improve UI usability and presentation as much as possible.
