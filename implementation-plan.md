# Implementation Plan: Northern Ireland Population Model

## Technology Stack
- **Database**: PostgreSQL (robust, web-compatible, excellent performance for 2M records)
- **ORM**: SQLAlchemy (Python standard, supports migrations, testing)
- **Containerization**: Kubernetes with Helm charts for all dependencies
- **Python Libraries**: pandas, numpy for data processing; pytest for testing

## Phase 0: Infrastructure Setup ✅ COMPLETED

### Step 0.1: Create Kubernetes Environment ✅ DONE
- **Implementation**: Kubernetes manifests for PostgreSQL, Redis, Python app deployment
- **Testing**: Test pod startup, service connectivity, persistent volume claims
- **Validation**: `kubectl get pods` shows all services running, database accepts connections

### Step 0.2: Setup Database with SQLAlchemy ✅ DONE
- **Implementation**: SQLAlchemy models, Alembic migrations, connection pooling
- **Testing**: Test model creation, migration up/down, connection handling
- **Validation**: Database schema matches models, migrations are reversible

## Phase 1: Project Foundation ✅ COMPLETED

### Step 1: Setup Project Structure ✅ DONE
- **Implementation**: Create src/ni_model/ and test/ directories with __init__.py files
- **Testing**: Verify package imports work correctly, test directory structure exists
- **Validation**: Run `python -c "import ni_model"` successfully

### Step 2: Configure Development Tools ✅ DONE
- **Implementation**: Create pyproject.toml with black, flake8, isort, pytest configurations
- **Testing**: Test linting passes on empty modules, pytest runs without errors
- **Validation**: Run `black --check .`, `flake8 .`, `isort --check .`, `pytest`

### Step 3: Create Core Database Schema ✅ DONE
- **Implementation**: Person table with PostgreSQL-optimized schema, indexes for performance
- **Testing**: Test schema creation, constraints, indexes, data type validation
- **Validation**: Create/drop tables successfully, insert 100K+ sample records with good performance

### Step 4: Implement Database Layer ✅ DONE
- **Implementation**: SQLAlchemy Person model, repository pattern, connection pooling
- **Testing**: Test CRUD operations, bulk operations, transaction handling, connection cleanup
- **Validation**: Handle 2M person records efficiently, proper connection pool management

## Phase 2: Simulation Engine Core ✅ COMPLETED

### Step 5: Build Simulation Engine Interface ✅ DONE
- **Implementation**: Abstract base class defining mandatory DB update pattern
- **Testing**: Test interface compliance, method signature validation, inheritance behavior
- **Validation**: Concrete implementations must follow interface contract

### Step 6: Create Population Manager ✅ DONE
- **Implementation**: PostgreSQL SAVEPOINT-based snapshots for zero-copy state management
- **Testing**: Test snapshot creation/restoration with testcontainers, population state consistency, rollback accuracy
- **Validation**: Multiple snapshot/rollback cycles maintain data integrity

### Step 7: Refactor Demographic Calculators ✅ DONE (CRITICAL REDESIGN)
- **Problem**: Current uniform-rate design cannot model NI-specific requirements (Catholic vs Protestant birth rates, age-specific rates, internal migration)
- **Solution**: Query-based cohort calculators + Model Director pattern

#### Step 7a: Refactor DemographicCalculator for Query-Based Cohorts ✅ DONE
- **Implementation**: 
  - Add query_filters to calculator constructor (religious_background, age_min, age_max, location, etc.)
  - Calculator applies rate only to matching population subset
  - Remove uniform rate logic from calculate() method
- **Testing**: Test calculator with various query filters, empty cohorts, overlapping cohorts
- **Validation**: Calculator correctly identifies and processes only matching population subset

#### Step 7b: Create ModelDirector for Model Composition ✅ DONE
- **Implementation**:
  - ModelDirector encapsulates model assumptions (e.g., "NI 2024 Base Model")
  - Configures multiple calculator instances with queries and rates
  - Example: Catholic women 20-35 (rate=15), Protestant women 20-35 (rate=11)
  - Provides simulate_births/deaths/migration methods that orchestrate all calculator instances
- **Testing**: Test director with multiple calculators, rate aggregation, cohort coverage
- **Validation**: Director correctly applies different rates to different demographic groups

#### Step 7c: Update SimulationEngine Integration ✅ DONE
- **Implementation**:
  - SimulationEngine accepts ModelDirector instead of individual calculators
  - Maintains mandatory sequential pattern: births→deaths→migration
  - ModelDirector handles internal orchestration of multiple calculator instances
- **Testing**: Test engine with ModelDirector, sequential execution, transaction handling
- **Validation**: Complete simulation cycle with demographic-specific rates produces expected changes

### Step 8: Build Simulation Orchestrator ✅ DONE
- **Implementation**: Coordinate sequential DB updates (births→deaths→migration→results)
- **Testing**: Test execution order, DB state after each step, transaction handling, error recovery
- **Validation**: Complete simulation cycle produces expected population changes

## Phase 3: Basic Model Implementation ✅ COMPLETED

### Step 9: Create Basic Demographic Model ✅ DONE
- **Implementation**: YAML-driven era-specific rates (Troubles/post-GFA/modern) via ModelDirector
- **Testing**: Test rate calculations, demographic transitions, boundary conditions
- **Validation**: Model produces realistic demographic changes over time

### Step 10: Generate Test Population Data ⏸ PARKED - moved to end
- See Phase 6

### Step 11: Implement Model Parameter System ✅ DONE
- **Implementation**: Configurable assumptions, rates, and model parameters
- **Testing**: Test parameter validation, default values, parameter persistence, invalid input handling
- **Validation**: Different parameter sets produce different but valid results

### Step 12: Add Results Generation ⏸ PARKED - moved to end
- See Phase 6

## Phase 4: Validation & Integration ⏸ PARKED - moved to end

### Step 13: Create Historical Validation Framework ⏸ PARKED - moved to end
- See Phase 7

### Step 14: Implement Model Comparison Tools ⏸ PARKED - moved to end
- See Phase 7

### Step 15: Add Integration Testing ⏸ PARKED - moved to end
- See Phase 7

## Phase 5: Web Visualisation Layer ✅ COMPLETED

### Step 16: Create REST API ✅ DONE
- **Implementation**: FastAPI application exposing simulation results. Endpoints:
  - `GET /api/population/summary` — total population, religious/gender breakdown
  - `GET /api/population/by-location` — population counts and religious breakdown per location
  - `GET /api/population/location/{location}` — drill-down detail for a single location (age bands, religion, gender, origin)
  - `GET /api/simulation/years` — list of completed simulation years available
  - `GET /api/population/by-year/{year}` — snapshot demographics for a given simulation year
- **Testing**: Test all endpoints, response schemas, error handling
- **Validation**: API returns correct aggregated data matching database state

### Step 17: Add Streaming Simulation Endpoint ✅ DONE
- **Implementation**: Server-Sent Events (SSE) endpoint `GET /api/simulation/stream?start_year=&end_year=` that:
  - Runs the simulation year-by-year server-side, caching each year's demographic snapshot as it completes
  - Emits all year snapshots immediately as they are computed (as fast as possible)
  - Emits a final `{event: "complete"}` message when done
  - Supports client disconnect/abort cleanly
- **Testing**: Test SSE event stream, per-year payload structure, disconnect handling
- **Validation**: Each emitted event contains correct population state for that year

### Step 18: Build NI Map Visualisation (Frontend) ✅ DONE
- **Implementation**: Single-page app (React + Leaflet.js) with NI GeoJSON map
  - Choropleth colouring by Catholic/Protestant/Other majority per county and Belfast area
  - Client buffers all incoming SSE year snapshots as they arrive
  - Play/Pause button controls playback of buffered snapshots at a human-readable pace
  - Speed control (e.g. 0.5x / 1x / 2x / 5x) adjusts ms-per-year interval independently of stream speed
  - Year display and progress bar update in real time during playback
  - Smooth colour transitions between years as demographic balance shifts
  - Scrub slider to jump to any already-buffered year
  - Click county/area to drill into location detail panel
- **Testing**: Component tests for map rendering, SSE buffering, play/pause, speed control, scrub
- **Validation**: Map updates at correct interval per speed setting, pause halts cleanly, scrub jumps correctly

### Step 19: Location Detail Drill-Down ✅ DONE
- **Implementation**: Detail panel shown on location click, also live-updating during playback:
  - Population total and trend chart (line graph across simulation years)
  - Religious breakdown pie/bar chart
  - Age pyramid
  - Origin breakdown (NI/ROI/GB/Other)
  - Net migration indicator
- **Testing**: Test data aggregation queries, chart data formatting, live update on SSE events
- **Validation**: Detail panel data matches raw database counts for selected location

## Phase 6: Realistic Data & Voting Predictions

### Step 19: Generate Test Population Data ✅ DONE (parked from Step 10)
- **Implementation**: Create realistic NI population dataset with proper distributions (age pyramid, Catholic/Protestant ~45/40/15 split, geographic spread across 10 locations, gender balance)
- **Testing**: Test data generation consistency, demographic distributions, data quality
- **Validation**: Generated population matches expected NI demographic patterns

### Step 20: Add Results Generation / Voting Predictions ✅ DONE (parked from Step 12)
- **Implementation**: Query final population state and generate voting predictions. VotingPredictor maps demographics → likely vote (Unite/Remain/Undecided) with configurable propensity rates by religious background, age, origin
- **Testing**: Test result accuracy, aggregation functions, output formatting
- **Validation**: Results reflect actual population changes from simulation

## Phase 7: Validation & Integration (parked from Phase 4)

### Step 21: Create Historical Validation Framework ✅ DONE (parked from Step 13)
- **Implementation**: Compare model predictions against actual historical data
- **Testing**: Test validation metrics, data comparison accuracy, statistical significance
- **Validation**: Model accuracy within acceptable thresholds for historical periods

### Step 22: Implement Model Comparison Tools ✅ DONE (parked from Step 14)
- **Implementation**: Compare different model implementations and parameters
- **Testing**: Test comparison metrics, statistical analysis, result visualization
- **Validation**: Clear differentiation between model performance

### Step 23: Add Integration Testing ✅ DONE (parked from Step 15)
- **Implementation**: End-to-end simulation testing with multiple scenarios
- **Testing**: Test complete workflows, error propagation, performance under load
- **Validation**: Full system operates correctly with realistic data volumes

## Testing Requirements
- Each step must achieve 90% code coverage
- All tests must pass before proceeding to next step
- Integration tests required for multi-component interactions
- Performance tests for database operations and simulation execution
- Docker containers must be used for all testing environments
- Database tests run against containerized PostgreSQL instance