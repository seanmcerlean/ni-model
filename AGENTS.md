# Repository development standards

These instructions apply to the entire repository. More-specific `AGENTS.md`
files may extend them for a subtree.

## General workflow

- Create and maintain a concise implementation plan for non-trivial work.
- Make code changes only when the user has requested implementation. The
  request may authorize a complete planned tranche; separate approval is not
  needed for each file within that scope.
- Preserve unrelated work and keep changes focused on the active objective.
- Add or update tests for every behavior change and defect fix.
- Do not commit changes unless the user explicitly asks for a commit.
- Before handoff or commit, run the relevant formatters, linters, type checks,
  unit tests, and integration tests. Clearly report any check that could not run.
- Target at least 90% coverage for maintained application code. Coverage is a
  quality signal, not a substitute for meaningful assertions and edge cases.

## Python backend

- Follow PEP 8 and keep source code under `src/` with tests under `test/`.
- Prefer single-purpose, Pythonic code. Apply the single-responsibility
  principle and remove meaningful duplication without creating opaque
  abstractions.
- Keep imports at module scope unless a documented circular-import or optional
  dependency constraint requires otherwise.
- Organize imports into standard-library, third-party, and local groups,
  separated by blank lines and alphabetized within each group.
- Use pytest for unit, integration, regression, and edge-case tests.
- The complete backend suite must remain runnable with `pytest test/`.
- Format with Black, sort imports with isort, and lint with flake8 using the
  checked-in project configuration.
- Validate untrusted API and configuration input at system boundaries.
- Keep stochastic model behavior reproducible through explicit local seeds;
  never depend on process-global random state.
- Document data provenance, definitions, transformations, and known
  limitations beside model inputs. Do not present assumptions as observed data.

## React and TypeScript frontend

- Keep frontend source under `frontend/src/` and colocate reusable behavior in
  focused components or hooks. Keep tests under `frontend/src/test/` unless a
  colocated test is materially clearer.
- Use strict TypeScript. Avoid `any`, unsafe type assertions, and duplicated
  backend response shapes; define shared frontend contracts in `types.ts`.
- Use function components and hooks. Keep render functions free of side
  effects, clean up timers/subscriptions/EventSource instances, and prevent
  stale asynchronous work from updating current UI state.
- Separate server-stream buffering, playback state, and presentation concerns.
  State must have one clear owner; derive values instead of synchronizing
  redundant copies.
- Handle loading, empty, complete, aborted, malformed-data, and network-error
  states visibly. Do not hide operational errors behind console output.
- Meet WCAG 2.1 AA fundamentals: semantic elements, keyboard operation, visible
  focus, associated labels, sufficient contrast, and text alternatives. Do not
  encode community or political information by colour alone.
- Prefer reusable CSS classes or a coherent styling layer over growing inline
  style objects. Keep the map and controls usable at narrow viewport widths.
- Test user-visible behavior with Vitest and Testing Library. Prefer accessible
  queries and user interactions over implementation-detail assertions.
- Add regression tests for stream lifecycle, playback timing, cleanup,
  validation, accessibility, and responsive-critical behavior.
- Run the checked-in frontend test, build, lint, and type-check scripts before
  handoff. Add those scripts/configurations when missing rather than relying on
  editor-only checks.

## Repository gates

From the repository root:

```bash
venv/bin/black --check src test
venv/bin/isort --check-only src test
venv/bin/flake8 src test
venv/bin/pytest test/
```

From `frontend/`:

```bash
npm test -- --run
npm run build
```

If additional `lint` or `typecheck` scripts are present, run those as well.
