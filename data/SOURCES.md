# Data sources

## Census 2021 baseline

The generator uses official NISRA Census 2021 marginal distributions:

| Model field | Definition | Source table |
|---|---|---|
| `age` | Five-year age band | MS-A02 |
| `gender` | Published census sex | MS-A07 |
| `religious_background` | Religion or religion brought up in by LGD; used as a community-background proxy | MS-B23 |
| `origin` | Country of birth; GB combines England, Scotland, and Wales | MS-A16 |

Source workbooks:

- [MS-A02 age](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a02.xlsx)
- [MS-A07 sex](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a07.xlsx)
- [MS-A16 country of birth](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a16.xlsx)
- [MS-B23 religion or religion brought up in](https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-b23.xlsx)

NISRA applies statistical disclosure control independently to output tables, so
their totals can differ from the headline Census population by a few people.
Weights therefore use each topic table's own denominator.

The model jointly samples LGD and community background from MS-B23, preserving
the large geographic differences needed by area scenarios. Age, sex and origin
remain independent marginals, so the generated population is not synthetic
Census microdata.

## Historical 1969 baseline

The historical model starts from NISRA's mid-1969 population estimate of
1,512,500. Its nearest authoritative age structure is the 1971 Census:
456,997 aged 0–14, 512,242 aged 15–39, 400,842 aged 40–64, and 165,984 aged 65
and over. The generator calibrates the modern five-year shape within each broad
band to those exact 1971 age shares and treats them as a documented 1969 proxy.

- [NISRA Census 2021 population bulletin, historical Census age table](https://datavis.nisra.gov.uk/census/census-2021-population-and-household-estimates-for-northern-ireland-statistical-bulletin-24-may-2022.html)
- [NISRA 1971 Census reports](https://www.nisra.gov.uk/publications/1971-census-reports)
- [CSO historical NI population table sourced from NISRA](https://www.cso.ie/en/releasesandpublications/ep/p-syi/psyi2018/appendix1-northernireland/northernirelandpeoplesociety/)

There is no equivalent 1971 joint table on current LGD boundaries. Iterative
proportional fitting preserves the documented estimated NI-wide community
shares while borrowing only the relative 2021 LGD pattern. Country-of-birth
shares are a conservative historical estimate (94% NI, 2.5% Ireland, 3% GB,
0.5% elsewhere). These spatial, community and origin distributions are clearly
labelled estimates rather than observed 1971 microdata.

## Population components, 2002–2024

`ni_population_components_2002_2024.csv` is a normalized copy of Figure 4 from
NISRA's accredited 2024 Mid-year Population Estimates release:

- [2024 Mid-year Population Estimates for Northern Ireland](https://datavis.nisra.gov.uk/population/2024-mid-year-estimates-for-northern-ireland.html)

It contains the published births, deaths, net migration, other changes, and
population reconciliation for each year ending mid-2002 through mid-2024.
Values are observations for calibration and back-testing, not future assumptions.

Downloaded and normalized on 2026-07-30. No values were interpolated.

## Current principal projection, 2024–2074

`ni_population_projection_2024_2074.csv` combines the observed rows for years
ending mid-2022 through mid-2024 above with NISRA's latest official principal
projection for years ending mid-2025 through mid-2074:

- [2024-based Population Projections for Northern Ireland](https://www.nisra.gov.uk/publications/2024-based-population-projections-northern-ireland)
- Source workbook: `NPP24_ppp_coc.xlsx`, published 28 April 2026.

The projection rows preserve population at start and end, births, deaths,
international plus cross-border inflows, corresponding outflows, and net
migration. The observed release only supplies net migration in its component
series, so inflow and outflow are intentionally blank for 2022–2024.
`reconciliation_adjustment` preserves NISRA's published `other changes` for
observed years and the small published rounding residual (between -7 and +6)
for projection years. It is retained for validation but is not applied as a
demographic event.

`scripts/build_current_model.py` extracts the official workbook and regenerates
both the normalized CSV and `models/ni_current.yaml`. It converts component
counts to rates per 1,000 using the population present at the exact point each
event runs (birth, then death, then inflow, then outflow). This accounts for the
simulation's sequential event order rather than applying every rate to the
opening population. The principal model has no random rate jitter: uncertainty
must be represented through explicit variants rather than noise around official
values.

The official publication cautions that projections are scenarios based on
demographic assumptions, not forecasts. The model carries that limitation in
its description.

### Current age-specific mortality

The current models preserve each year's observed or principal-projection crude
death rate, but select deaths using the all-person 2024 age-specific rates in
Table 5.3 of NISRA's Registrar General Annual Report. The rates per 1,000 are
4.424556 at age 0; 0.091557 at 1–4; 0.073626 at 5–9; 0.030976 at 10–14;
0.466414 at 15–24; 0.836050 at 25–34; 1.455992 at 35–44; 2.839962 at 45–54;
7.009875 at 55–64; 16.609164 at 65–74; 44.028801 at 75–84; and 149.379433
at 85+. These values determine relative individual risk; the active annual
crude rate still determines the total number selected, so projected yearly
death totals are not accidentally replaced by the 2024 population structure.

- [NISRA Registrar General Annual Report 2024 deaths tables](https://www.nisra.gov.uk/publications/registrar-general-annual-report-2024-deaths)

### Community-differentiated sensitivity variant

`ni_current_community.yaml` retains every annual NISRA principal-projection
component total but splits birth, death, immigration and emigration rates by
community background. The relative multipliers are conservative scenario
assumptions calibrated to the direction and scale of Census 2011–2021 change:
Catholic-background counts increased 6%, Protestant-background counts decreased
6%, Other increased 72%, and None increased 75%. Those changes combine natural
change, migration, response change and secularisation; published Census totals
cannot identify separate component rates. The variant therefore must not be
described as an observed or official community projection, and it does not
model people changing background.

For each component, multipliers are normalized against the Census 2021
community shares so their starting weighted rate equals the corresponding
official NI-wide rate. As cohort shares diverge later, small differences from
the aggregate principal total are an intentional scenario outcome.

## Map boundaries

- **Producer:** Office for National Statistics, using OSNI boundary data.
- **Layer:** Local Authority Districts (December 2024), generalised 20-metre
  boundaries, filtered to the 11 Northern Ireland LGDs (`N09` codes).
- **Licence:** UK Open Government Licence.
- **Transform:** The ArcGIS service returns WGS84 GeoJSON with a 0.002-degree
  maximum offset for browser display in `frontend/src/geo/ni.geojson`.

The frontend and model now use one consistent current geography. The boundary
codes join directly to the Census and migration tables.

## Internal migration between LGDs

`ni_internal_migration_lgd_2021.csv` is extracted from NISRA Census 2021 public
origin–destination table ODMG01NI-UK. It contains all 110 directed movements
between different LGDs during the year before Census day, totalling 38,074
people. Rates use the exact Census 2021 source-LGD population in
`ni_census_2021_lgd_population.csv` as denominator.

- [Census 2021 origin–destination migration tables](https://www.nisra.gov.uk/publications/census-2021-origin-destination-migration-tables-uk)
- [Census 2021 LGD population table](https://build.nisra.gov.uk/en/custom/data?d=PEOPLE&v=LGD14)
- [NISRA migration methodology](https://datavis.nisra.gov.uk/population/methodology_report.html)

These are observed one-year Census flows, not a forecast. The current model
holds their per-origin-population rates constant after 2021 as a documented
estimate. Census 2021 took place during pandemic restrictions, and NISRA notes
that migration outputs may have been affected. The simulation selects all
origin–destination moves from the pre-move population and applies them
simultaneously, preventing rule order from moving a person twice.

## Assumptions not yet replaced

- education is conditionally sampled from hand-authored age assumptions.
- mortality by age, community-specific fertility, and internal migration rates
  in `models/ni_base_2024.yaml` remain assumptions.
- voting propensities remain scenario parameters, not observed vote-intention
  estimates.
