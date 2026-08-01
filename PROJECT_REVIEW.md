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

### Work ledger

- [x] Current models preserve annual projected death totals while selecting
  deaths with NISRA 2024 age-specific mortality rates.
- [x] Items appear in a consistent semantic order in the area details.
- [x] Each frontend run starts with a random, visible seed that remains editable.
- [x] Historical models start in 1969 from a documented 1,512,500 population;
  the 1971 Census broad-age marginals are used as a clearly labelled proxy.
- [x] Frontend has a single toggle to select a representative sample or all
  available baseline rows, while reported totals retain real population scale.
- [x] Custom overall polling baselines reweight LucidTalk subgroup odds on
  demand, preserving demographic and area differences without stored
  person-level political scores.
- [ ] Add MCP functionality in addition to the APIs so an AI could interact if desired. Use FastMCP 4

Performance work is tracked separately in `performance.md`.
