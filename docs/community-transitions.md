# Community-background calibration

The population stores the Census **religion or religion brought up in** measure
as a practical proxy for community background. It is not current religious
practice and it is not vote intention.

## Causal pipeline

The historical model separates mechanisms instead of rewriting checkpoint
outputs:

1. NISRA annual births, deaths, and population adjustments anchor the expected
   size of each demographic component. The simulation remains stochastic.
2. Bounded community-specific fertility, mortality, and migration multipliers
   allocate those components between groups.
3. A newborn receives a background from a birth-year-specific probability
   matrix conditional on one sampled parent's background. This is an explicit
   reduced-form approximation; the model does not construct couples.
4. From 2001, bounded adult transitions to None represent effective change in
   the reported Census category. They are not interpreted as literal changes
   in upbringing.

The stage never reads a target community share and never adds, removes, or
relabels people to make a checkpoint match.

## Evidence

NISRA Census 2021 commissioned table CT0156 anchors the modern newborn matrix.
It reports dependent-child backgrounds for family background combinations. The
one-parent matrix aggregates those household combinations into a tractable
conditional estimate and is therefore not a claim about biological inheritance.

Annual births and deaths are observed NISRA registrations. From 2001, population
adjustment uses published mid-year components. Before 2001 it is the accounting
residual from annual population, birth, and death series, so it includes timing
differences and revisions as well as migration.

No published longitudinal matrix directly measures annual change in the
combined four-category Census proxy. Adult response-category rates and the
pre-2011 newborn probabilities are consequently bounded estimates.

## Calibration and non-overfitting

The harness searches causal inputs against 2001 and 2011 only. It evaluates each
candidate across multiple deterministic seeds and accepts a broad region:
population within 5% and every community share within 2.5 percentage points. It
then chooses a central accepted parameter set, not the lowest-error trajectory.
The 2021 Census is a held-out validation and cannot affect selection.

Inputs are in
[`data/historical_demographic_components.yaml`](../data/historical_demographic_components.yaml),
and the selected ensemble result, seed spread, limitations, and tolerances are
in
[`data/historical_calibration_result.yaml`](../data/historical_calibration_result.yaml).
Run the harness with:

```bash
venv/bin/python scripts/calibrate_historical.py \
  --iterations 32 --sample-size 1500 --seed 48 --workers 4 --replicates 3
```

Different seeds produce different individual histories and aggregate results.
Meeting a tolerance means representative, not exact.
