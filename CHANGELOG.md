# Changelog

## 0.2.2 - 2026-07-30

### Added

- Model discovery, selection, assumption details, and a zero-net-migration
  sensitivity scenario.
- Overall annual statistics and separate immigration/emigration results.
- Live per-area community, gender, origin, and age-band snapshots.
- Sourced OSNI county and Belfast constituency map boundaries.

### Changed

- Redesigned the dashboard, playback controls, map tooltips, and area panel.
- Area panels now follow the active playback year.
- Map colours use green for Catholic background, blue for Protestant
  background, and slate for balanced areas.
- Community-background statistics show the complete four-category split.

## 0.2.1 - 2026-07-30

### Fixed

- Corrected malformed NI map polygon nesting that caused Leaflet to render a
  blank page.
- Added a regression test for valid GeoJSON polygon coordinate rings.

## 0.2.0 - 2026-07-30

### Added

- Repository-wide backend and frontend development standards.
- NISRA Census 2021 data provenance and exact marginal baseline distributions.
- NISRA observed population components for 2002–2024 with reconciliation tests.
- Seeded per-run randomness and model-configuration validation.
- Annual population ageing.
- Project purpose, limitations, and priority review.

### Fixed

- Community background no longer mixes incompatible current-religion categories.
- Implausible centenarian and country-of-birth generator weights.
- Births can only be assigned through women aged 15–49 in the selected cohort.
- API model paths cannot escape the `models/` directory.
- Synchronous simulation snapshots are captured in their actual simulated year.
- Deprecated SQLAlchemy declarative-base import.
