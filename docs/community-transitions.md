# Community-transition methodology

The population stores the Census-style **religion or religion brought up in**
category as a practical proxy for community background. It is not the same as
current religious affiliation, and neither measure is a direct vote intention.

The annual integration stage allows adult records to move between Catholic,
Protestant, Other and None after migration. Competing transitions are selected
from the start-of-stage population and applied simultaneously, so nobody can
move through two categories in one year. These changes affect community and
political aggregates but never create or remove people.

## Evidence and calibration

No published annual longitudinal transition matrix exists for these four
community-background categories. The model therefore labels every rate as an
estimate and keeps it independently adjustable.

- NISRA Census 2021 commissioned table CT0156 shows how dependent children's
  recorded backgrounds vary in mixed, None and Other family combinations. It
  establishes that categories are not perfectly inherited, but is
  cross-sectional rather than an annual transition measure.
- Doebler and Shuttleworth's analysis of linked 2001–2011 NILS records supplies
  direction, age pattern and relative Catholic/Protestant differences. It
  measures current affiliation, so the model deliberately uses only a small
  fraction of its observed switching levels.
- Census 2011 and 2021 category totals provide aggregate plausibility bounds.
- NILT is used only to check broad direction and age patterns. Its raw current-
  affiliation percentages do not set model levels or transition rates.

The numeric assumptions and source URLs live in
[`data/community_transition_assumptions.yaml`](../data/community_transition_assumptions.yaml).
Defaults concentrate changes at ages 18–44, make direct Catholic–Protestant
transitions rare, and allow movement both into and out of None and Other. This
prevents those categories being treated as irreversible demographic sinks.

## Interpretation

Outputs should be described as **estimated community-category transitions**,
not observed conversions or loss of upbringing. Long-range results are scenario
projections. Use the global or per-source-community integration multiplier for
sensitivity analysis, including zero for an immutable-category counterfactual.
