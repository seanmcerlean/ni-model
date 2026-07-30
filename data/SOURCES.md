# Data sources

## Census 2021 baseline

The generator uses official NISRA Census 2021 marginal distributions:

| Model field | Definition | Source table |
|---|---|---|
| `age` | Five-year age band | MS-A02 |
| `gender` | Published census sex | MS-A07 |
| `religious_background` | Religion or religion brought up in; used as a community-background proxy | MS-B23 |
| `origin` | Country of birth; GB combines England, Scotland, and Wales | MS-A16 |

Source workbooks:

- [MS-A02 age](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a02.xlsx)
- [MS-A07 sex](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a07.xlsx)
- [MS-A16 country of birth](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a16.xlsx)
- [MS-B23 religion or religion brought up in](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-b23.xlsx)

NISRA applies statistical disclosure control independently to output tables, so
their totals can differ from the headline Census population by a few people.
Weights therefore use each topic table's own denominator.

The model samples these as independent marginals. It does not yet reproduce
their joint distributions (for example age by community background or origin by
location), so a generated population is plausible in aggregate but is not
synthetic Census microdata.

## Population components, 2002–2024

`ni_population_components_2002_2024.csv` is a normalized copy of Figure 4 from
NISRA's accredited 2024 Mid-year Population Estimates release:

- [2024 Mid-year Population Estimates for Northern Ireland](https://datavis.nisra.gov.uk/population/2024-mid-year-estimates-for-northern-ireland.html)

It contains the published births, deaths, net migration, other changes, and
population reconciliation for each year ending mid-2002 through mid-2024.
Values are observations for calibration and back-testing, not future assumptions.

Downloaded and normalized on 2026-07-30. No values were interpolated.

## Assumptions not yet replaced

- `location` uses a non-standard mix of six historic counties and four Belfast
  areas and remains synthetic.
- education is conditionally sampled from hand-authored age assumptions.
- mortality by age, community-specific fertility, and internal migration rates
  in `models/ni_base_2024.yaml` remain assumptions.
- voting propensities remain scenario parameters, not observed vote-intention
  estimates.
