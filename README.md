# Northern Ireland Population & Voting Model

A demographic simulation system that models Northern Ireland's ~2 million population at individual person level. Runs iterative year-by-year simulations (births → deaths → migration) and generates voting predictions from the resulting population state.

## What it does

- Maintains a full individual-level population in PostgreSQL (~2M person records)
- Simulates demographic change year-by-year using configurable, era-specific rates
- Applies different rates to different cohorts (e.g. Catholic vs Protestant birth rates, age-specific mortality)
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

The simulation follows a mandatory sequential DB-update pattern per year:

```
generate births → INSERT rows → remove deaths → DELETE rows → apply migration → UPDATE rows → snapshot results
```

Model assumptions are defined in YAML and loaded at runtime via `ModelDirector`. Snapshots use PostgreSQL SAVEPOINTs for zero-copy rollback.

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
| GET | `/api/simulation/years` | List of completed simulation years |
| GET | `/api/simulation/stream` | SSE stream — runs simulation and emits year snapshots |
| POST | `/api/simulation/run` | Run simulation synchronously |

SSE stream example:
```
GET /api/simulation/stream?start_year=1971&end_year=2024&model_path=models/ni_base_2024.yaml
```

Each event contains a full demographic snapshot for that year. A final `event: complete` signals the end.

## Model configuration

Models are defined in YAML. The default model is `models/ni_base_2024.yaml`.

```yaml
name: "NI Historical Model"
rate_jitter: 0.05   # ±5% random variation per year

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
    destination: "BELFAST_WEST"
    filters:
      age_min: 18
      age_max: 35
      location: "DERRY"
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

Current coverage: **97.86%** across 205 tests.

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

## Data sources

- Population benchmarks: [NISRA Census](https://www.nisra.gov.uk/statistics/census) 1971–2021
- Geographic boundaries: NI GeoJSON (10 locations: Belfast N/S/E/W, Antrim, Armagh, Down, Derry, Fermanagh, Tyrone)
- Demographic rates: derived from NISRA vital statistics and academic literature
