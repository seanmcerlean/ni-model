# Northern Ireland Population & Voting Model

A demographic simulation system that models Northern Ireland's ~2 million
population at individual person level. Runs iterative year-by-year simulations
(ageing → births → deaths → migration) and generates voting scenarios from the
resulting population state.

## What it does

- Maintains an immutable baseline plus isolated per-run populations in
  PostgreSQL (~2M person records per active run)
- Simulates demographic change year-by-year using configurable, era-specific rates
- Applies different rates to different cohorts (e.g. community-background birth rates and age-specific mortality)
- Tracks internal migration between NI locations and external migration in/out
- Generates border poll voting predictions (Unite/Remain/Undecided) from the simulated population
- Validates model output against NISRA census benchmarks (1971–2021)
- Streams simulation results in real time via SSE to a React/Leaflet map visualisation

## Architecture

```
src/ni_model/
├── api/            # FastAPI — REST endpoints + SSE stream
├── core/           # SQLAlchemy models, database session
├── data/           # Population generator, repository pattern
├── simulation/     # Engine, orchestrator, calculators, model director, voting predictor
└── validation/     # Historical validator, model comparator
```

Each simulation has a durable run ID. Its cloned population is isolated from
other users, and every completed year is persisted as an aggregate snapshot.
The simulation follows a sequential DB-update pattern per year:

```
age all residents → generate births → remove deaths → apply migration → snapshot
```

Model assumptions are defined in YAML and loaded at runtime via
`ModelDirector`. Restoring a run resets it from the immutable baseline;
snapshots and run status survive API restarts.

The run editor supports global and per-community multipliers for births,
deaths, external migration and internal relocation. These are sensitivity
controls: they alter an isolated run and do not rewrite the sourced model.

## Quick start

**Prerequisites:** Python 3.11+, PostgreSQL (or use the Kubernetes setup below)

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start the API
uvicorn src.ni_model.api.app:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Full-scale PostgreSQL baseline

The Compose workflow builds the application and reproducibly seeds an exact-size
Census 2021 baseline of 1,903,175 resident records. The named volume is retained,
and the idempotent seed job skips a database that already has a baseline.

```bash
docker compose up --build
```

The API and built frontend are then available at `http://localhost:8000`.
Seeding uses batches of 25,000 so memory use does not grow with the population.

A separate, opt-in 1,536,065-record 1971-scale database is available for
engineering and performance testing:

```bash
docker compose --profile historical up historical-seed
```

That historical baseline is a **best-effort representative estimate**, not a
perfect reconstruction: only its total and legacy community-background
assumptions are historical; age, current-LGD, country-of-birth and education
distributions use the current generator. Treat those fields as estimates and do
not present them as observed 1971 data.

## Kubernetes deployment

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/app.yaml
```

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/population/summary` | Total population, religious/gender breakdown |
| GET | `/api/population/by-location` | Population counts per location |
| GET | `/api/population/location/{location}` | Drill-down: age bands, religion, gender, origin |
| GET | `/api/population/by-year/{year}` | Demographic snapshot for a simulated year |
| GET | `/api/simulation/runs` | List durable simulation runs |
| GET | `/api/simulation/runs/{run_id}` | Run status and completed years |
| GET | `/api/simulation/runs/{run_id}/years/{year}` | Durable year snapshot |
| GET | `/api/simulation/stream` | SSE stream — creates an isolated run and emits year snapshots |
| POST | `/api/simulation/run` | Run simulation synchronously |

SSE stream example:
```
GET /api/simulation/stream?start_year=1971&end_year=2024&model_path=models/ni_base_2024.yaml
```

Each event contains the run ID and full demographic snapshot for that year.
The response also exposes `X-Simulation-Run-ID`; a final `event: complete`
signals the end. Run populations and snapshots are deleted together when the
run is explicitly removed (a deletion endpoint is not yet exposed).

## Model configuration

Models are defined in YAML. The default model is `models/ni_base_2024.yaml`.

```yaml
name: "NI Historical Model"
rate_jitter: 0.05   # ±5% random variation per year
random_seed: 42     # reproducible run when population/config are unchanged

birth_rates:
  - rate: 26.0
    year_min: 1969
    year_max: 1994
    filters:
      religious_background: "CATHOLIC"

death_rates:
  - rate: 50.0
    year_min: 2010
    filters:
      age_min: 71
      age_max: 85

migration_rates:
  - rate: -8.0
    year_min: 1969
    year_max: 1994
    filters: {}

internal_migration_rates:
  - rate: 15.0
    destination: "BELFAST"
    filters:
      age_min: 18
      age_max: 35
      location: "DERRY_STRABANE"
```

Rates are per 1,000 of the matching cohort. Filters can combine `religious_background`, `age_min`, `age_max`, `location`, and `gender`.

## Frontend

A React + Leaflet.js single-page app visualises simulation output as a choropleth map of NI.

```bash
cd frontend
npm install
npm run dev      # dev server at http://localhost:5173
npm run build    # production build → frontend/dist/
```

Features: play/pause, speed control (0.5×–5×), scrub slider, per-location drill-down panel with population trend, religious breakdown, age pyramid, and origin breakdown.

## Testing

```bash
# Full test suite (unit + integration)
venv/bin/pytest test/

# Integration tests only (requires Docker for testcontainers)
venv/bin/pytest test/integration/

# With coverage report
venv/bin/pytest test/ --cov=src/ni_model --cov-report=html
```

The suite includes unit, API, and PostgreSQL integration tests. Database-backed
tests require a working Docker daemon because they use testcontainers.

## Linting

```bash
venv/bin/black src/ test/
venv/bin/isort src/ test/
venv/bin/flake8 src/ test/
```

## Historical validation

The validator compares simulation snapshots against NISRA census data for 1971, 1981, 1991, 2001, 2011, and 2021. Benchmarks are in `data/historical_benchmarks.yaml`. The default acceptance threshold is 10% MARE (mean absolute relative error).

```python
from src.ni_model.validation.historical_validator import HistoricalValidator

validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
result = validator.validate(2021, snapshot)
print(result.accuracy_score)   # 0.0–1.0
print(result.within_threshold) # True if MARE <= 10%
```

## Data provenance and interpretation

- The 2021 population, sex, age structure, and community-background baseline is
  grounded in [NISRA Census 2021](https://www.nisra.gov.uk/statistics/census/2021-census).
- `religious_background` currently represents NISRA's **religion or religion
  brought up in** measure, used here as a community-background proxy. It does
  not represent current religious practice or voting intention.
- NISRA only provides this comparable combined measure from 2001. The 1971–1991
  benchmark entries remain legacy estimates and are explicitly flagged in the
  YAML pending reconstruction from historical source tables.
- Geographic location and education weights and most demographic rates remain
  model assumptions, not fully sourced observations. They must be calibrated
  before interpreting forecasts as estimates.
- Official births, deaths, net migration, and population reconciliation for
  2002–2024 are checked in for calibration and back-testing. See
  [`data/SOURCES.md`](data/SOURCES.md) for definitions and direct source files.
- Border-poll outputs are scenarios based on configurable propensity assumptions.
  They are not forecasts validated against observed referendum results (no
  Northern Ireland border poll has occurred).
