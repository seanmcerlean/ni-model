# Northern Ireland Population & Voting Model

A demographic simulation system that models Northern Ireland's ~2 million
population at individual person level. Runs iterative year-by-year simulations
(ageing → births → deaths → migration → community transition) and generates voting scenarios from the
resulting population state.

## Deployment modes

From WSL, run the application with mode and host port as command-line options:

```bash
./run.sh --mode parquet --port 8000
```

From Windows PowerShell, run the same deployment inside WSL:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-wsl.ps1 -Mode parquet -Port 8000
```

Check the WSL/Docker dependencies from Windows without starting the app:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-wsl.ps1 -CheckDependencies
```

The Windows launcher handles repositories stored either inside WSL or on a
Windows drive, opens the correct WSL directory and invokes `run.sh`. It infers
the distribution from a `\\wsl.localhost\Distro\...` path; set
`NI_MODEL_WSL_DISTRO` in Windows to override it. `run-wsl.cmd` is also provided
for Windows-drive checkouts where a Command Prompt launcher is preferred.

Both options are optional and default to `parquet` and `8000`. Check the only
host dependencies—Docker, Docker Compose v2 and a running Docker daemon—with:

```bash
./check-dependencies.sh
```

`run.sh` performs the same check automatically before deployment. The lower-level
`deploy.sh` interface remains available through `NI_MODEL_MODE` and
`NI_MODEL_PORT`.

| Mode | Purpose | Population storage |
|---|---|---|
| `parquet` | Default local/WSL deployment with configurable runs | Immutable full baselines in Parquet; SQLite stores local run metadata |
| `static` | ChatGPT Sites or static hosting | Recorded full-population aggregate JSON only |
| `full` | Durable multi-user/server deployment | PostgreSQL, API worker, events and checkpoints |

```bash
./deploy.sh                         # default Parquet mode
NI_MODEL_MODE=static ./deploy.sh   # generate and serve recorded site
NI_MODEL_MODE=full ./deploy.sh     # existing PostgreSQL deployment
```

The first Parquet or static deployment creates deterministic `current` and
`historical` full-population baselines under `data/baselines/`. Static mode
then records every model exposed by the frontend selector. The historical,
current, community and zero-migration recordings use seeds 1180, 1690, 1921
and 1969 respectively. Historical playback is fixed at 1969–2024; future
recordings are fixed at 2021–2075. Generated population and recording files are
local build artifacts and are not committed.

Static mode fixes seeds, demographic multipliers and year ranges. Model selection, year
playback, maps, community display, polling selection, undecided treatment and
polling shocks remain browser-side. Parquet and full modes allow demographic
assumptions, seeds and a shorter end year to change; every run still starts from
the selected model's observed baseline year so demographic history is never skipped.

### Hosted static deployments

The repository includes two deployment scripts. They are infrastructure
starting points and have **not been executed against either hosting provider**.
Review the generated resources, account permissions, current pricing and
provider limits before running them.

Build the deployable static directory without publishing it:

```bash
scripts/build_static_site.sh
```

Pass `--refresh-recordings` to regenerate all four full-population recordings
unconditionally. Otherwise the builder verifies the schema, model catalogue,
source inputs, complete asset set and both Parquet baselines, regenerating all
recordings whenever anything is stale. Output is written to the ignored
`build/static-site/` directory.

AWS deployment uses CloudFormation to create a private encrypted S3 bucket,
CloudFront distribution and origin-access control, then uploads the site and
invalidates the cache. AWS CLI v2 credentials are required, and S3/CloudFront
can incur charges:

```bash
deploy/aws-static.sh --stack ni-model-static --region eu-west-2
```

The free-hosting option uses Cloudflare Pages. Create a Pages project and API
token with Pages edit permission, then run:

```bash
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
export CLOUDFLARE_API_TOKEN="your-api-token"
deploy/cloudflare-pages.sh --project ni-model --branch main
```

Cloudflare Pages has a free plan suitable for these static aggregate files,
subject to its [current platform limits](https://developers.cloudflare.com/pages/platform/limits/).
Neither hosted mode uploads the individual-level Parquet baseline.

## What it does

- Evolves complete 1,903,175-person current and 1,512,500-person historical
  baselines without sending individual records to the browser
- Supports Parquet/SQLite for portable local runs, aggregate JSON for static
  playback, and PostgreSQL for durable multi-user operation
- Simulates demographic change year-by-year using configurable, era-specific rates
- Applies different rates to different cohorts (e.g. community-background birth rates and age-specific mortality)
- Tracks internal migration between NI locations and external migration in/out
- Models estimated adult transitions between community-background categories
- Generates border poll voting predictions (Unite/Remain/Undecided) from the simulated population
- Validates model output against NISRA census benchmarks (1971–2021)
- Streams simulation results in real time via SSE to a React/Leaflet map visualisation
- Exposes the same read, simulation and polling workflows to AI clients over MCP

## Architecture

```
src/ni_model/
├── api/            # FastAPI — REST endpoints + SSE stream
├── core/           # SQLAlchemy models, database session
├── data/           # Population generator, repository pattern
├── mcp/            # FastMCP 4 tools over HTTP or stdio
├── simulation/     # Engine, orchestrator, calculators, model director, voting predictor
└── validation/     # Historical validator, model comparator
```

Live simulations have a run ID and load the selected immutable baseline into
compact Polars/Arrow columns. The browser receives aggregate snapshots rather
than individual rows. Parquet mode uses an embedded worker, SQLite run metadata
and local checkpoints; full mode uses PostgreSQL, a durable job queue, a
separate worker and persisted events. Static mode has no API or database and
replays pre-generated aggregate snapshots. All simulation modes use the same
sequential semantics per year:

```
derive age → generate births → remove deaths → apply migration → relocate →
apply community transition → snapshot
```

Model assumptions are defined in YAML and loaded at runtime via
`ModelDirector`. In full mode, PostgreSQL provides the durable `SKIP LOCKED`
job queue; snapshots, events, checkpoints, cancellation, and run status survive
API and worker restarts.

Public deployments can bound anonymous-client concurrency and horizons with
`MAX_ACTIVE_RUNS_PER_USER` and `MAX_SIMULATION_HORIZON_YEARS`. Worker execution,
retention, and checkpoint storage are controlled by
`SIMULATION_TIMEOUT_SECONDS`, `SIMULATION_RETENTION_DAYS`, and
`MAX_CHECKPOINT_BYTES_PER_RUN`.

Browser runs are isolated with an opaque, HTTP-only owner cookie. This prevents
one browser from listing or manipulating another browser's REST runs, but it is
not user authentication. Put full mode behind an authentication proxy before
exposing it to an untrusted network; static mode remains the preferred public
deployment.

The run editor supports global and per-community multipliers for births,
deaths, external migration, internal relocation and community transition. These are sensitivity
controls: they alter an isolated run and do not rewrite the sourced model.

## Local development without Compose

The Docker launcher above is the supported quick start. For backend development
without Compose, install Python 3.11+ and configure PostgreSQL explicitly:

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run database migrations
export NI_MODEL_MODE=full
export DATABASE_URL=postgresql://ni_user:ni_password@localhost:5432/ni_current
alembic upgrade head

# Start the API
uvicorn src.ni_model.api.app:app --reload
```

The API is available at `http://localhost:8000`. Interactive docs are at
`http://localhost:8000/docs`, and the MCP endpoint is
`http://localhost:8000/mcp/`.

The MCP interface uses the FastMCP 4 beta and MCP 2 protocol types. It provides
model discovery, baseline and area statistics, custom polling scenarios,
durable simulation control, aggregate year snapshots, and bounded inspection
of individual histories. It deliberately does not expose destructive run
deletion. To use a local stdio transport instead:

```bash
venv/bin/python scripts/mcp_server.py
```

### Full-scale PostgreSQL baseline

The Compose workflow builds the application and reproducibly seeds an exact-size
Census 2021 baseline of 1,903,175 resident records. The named volume is retained,
and the idempotent seed job skips a database that already has a baseline.

```bash
docker compose up --build
```

The API and built frontend are then available at `http://localhost:8000`, or
the host port supplied through `NI_MODEL_PORT`.
Seeding uses batches of 25,000 so memory use does not grow with the population.

A separate, opt-in 1,512,500-record historical database is available for
engineering and performance testing:

```bash
docker compose --profile historical up historical-seed
```

That 1969 baseline is a **best-effort representative estimate**, not a perfect
reconstruction. Its total is sourced for 1969 and its broad age distribution
uses the 1971 Census as the nearest documented proxy. Community background and
other unavailable joint distributions remain estimates, and current LGDs are
used as stable simulation areas rather than claimed historical boundaries.

## API endpoints

These endpoints are available in Parquet and full modes. Static hosting has no
server API and serves only the recorded aggregate JSON used by the frontend.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/population/summary` | Total population, religious/gender breakdown |
| GET | `/api/population/by-location` | Population counts per location |
| GET | `/api/population/location/{location}` | Drill-down: age bands, religion, gender, origin |
| GET | `/api/simulation/runs` | List durable simulation runs |
| GET | `/api/simulation/runs/{run_id}` | Run status and completed years |
| GET | `/api/simulation/runs/{run_id}/years/{year}` | Durable year snapshot |
| GET | `/api/simulation/stream` | Queue a run and stream completed aggregate year snapshots |
| POST | `/api/simulation/run` | Queue a durable background simulation |
| POST | `/api/simulation/runs/{run_id}/cancel` | Cooperatively cancel a queued/running simulation |
| DELETE | `/api/simulation/runs/{run_id}` | Delete a terminal run, events, snapshots, and checkpoints |
| GET | `/api/simulation/runs/{run_id}/years/{year}/people` | Filtered, paginated individual population state |
| GET | `/api/simulation/runs/{run_id}/people/{person_id}/history` | Inspect one resident's initial state and events |
| MCP | `/mcp/` | FastMCP 4 discovery and tool calls over HTTP |

SSE stream example:
```
GET /api/simulation/stream?start_year=1969&end_year=2024&model_path=models/ni_base_2024.yaml
```

The first event is the unchanged observed baseline and reports zero demographic
events; changes are applied from the following year. Each event contains the
run ID and full demographic snapshot for that year.
The response also exposes `X-Simulation-Run-ID`; a final `event: complete`
signals the end. Run events, snapshots and checkpoints are deleted together
through the terminal-run deletion endpoint.

## Model configuration

Models are defined in YAML. The frontend defaults to the community-differentiated
current model, `models/ni_current_community.yaml`; the historical model remains
selectable.

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

`integration_rates` use the same filters and add a destination community. They
represent an estimated change in the reported model category, are applied
simultaneously after migration, and do not change population.
`child_background_rules` provide a time-varying probability distribution for a
newborn conditional on one sampled parent's background. Neither mechanism is a
claim that upbringing literally changes. The causal calibration, evidence
boundary, and one-parent approximation are documented in
[the community-transition methodology](docs/community-transitions.md).

Immigrant community, origin and LGD profiles use the documented model inputs.
Until a sourced migrant age-by-LGD series is added, immigrant ages use the
evolving resident age distribution as an explicit proxy; education values are
kept compatible with age.

## Frontend

A React + Leaflet.js single-page app visualises simulation output as a choropleth map of NI.

```bash
cd frontend
npm install
npm run dev      # dev server at http://localhost:5173
npm run build    # production build → frontend/dist/
```

Features include play/pause, speed control (0.5×–5×), a scrub slider, blended
Unite/Remain and community map modes, probable-community display, per-location
demographic and political detail, LucidTalk polling calibrations, reported or
decided-voter presentation, and frontend-only neutral/Brexit/anti-Brexit polling
shock scenarios.

## Performance benchmarks

Benchmarks run against an already seeded PostgreSQL database and use a fixed
random seed. They report wall and CPU time, SQL statements, affected rows, peak
resident memory, stored population totals, and aggregate SSE payload size for
each simulation stage.

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ni_model \
  venv/bin/python scripts/benchmark_simulation.py \
  --expected-size 25000 \
  --start-year 2025 \
  --end-year 2025 \
  --output benchmark-25k.json
```

Use separately seeded 25,000, 250,000, and 1,903,175-person databases for the
three standard workloads. `--expected-size` prevents accidentally recording a
result against the wrong baseline. Benchmark JSON includes the model, seed,
years, platform, and Python version so results can be compared reproducibly.

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
- `probable_community` is a separate Catholic, Protestant, or Other ecological
  lineage estimate for reported None records. It is selectable, never replaces
  the Census field, and is not an observed identity or vote. See
  [`docs/probable-community.md`](docs/probable-community.md).
- NISRA only provides this comparable combined measure from 2001. The 1971–1991
  benchmark entries remain legacy estimates and are explicitly flagged in the
  YAML pending reconstruction from historical source tables.
- Historical aggregate births and deaths are sourced observations; pre-2001
  population adjustment and community-specific differentials remain clearly
  labelled estimates. Geographic location and education weights are also model
  assumptions.
- Official births, deaths, net migration, and population reconciliation for
  2002–2024 are checked in for calibration and back-testing. See
  [`data/SOURCES.md`](data/SOURCES.md) for definitions and direct source files.
- Border-poll outputs are scenarios based on configurable propensity assumptions.
  They are not forecasts validated against observed referendum results (no
  Northern Ireland border poll has occurred).
