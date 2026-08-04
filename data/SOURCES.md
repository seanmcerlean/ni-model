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
proportional fitting preserves the causally calibrated estimated NI-wide
community shares while borrowing only the relative 2021 LGD pattern. The
community starting point is not a 1969 observation: it is selected by the
historical calibration described below. Country-of-birth
shares are a conservative historical estimate (94% NI, 2.5% Ireland, 3% GB,
0.5% elsewhere). These spatial, community and origin distributions are clearly
labelled estimates rather than observed 1971 microdata.

## Historical components and community calibration, 1969–2021

`historical_demographic_components.yaml` uses NISRA registration-year births
and deaths and annual mid-year population estimates. From 2001 its population
adjustment is NISRA's published migration-and-other-changes component. Before
2001 it is the explicit accounting residual, so it is labelled as an estimate
and not as observed migration.

- [NISRA births 1887–2021](https://www.nisra.gov.uk/publications/birth-statistics)
- [NISRA deaths 1887–2021](https://www.nisra.gov.uk/publications/death-statistics)
- [NISRA 2024 mid-year population estimates and components](https://www.nisra.gov.uk/publications/2024-mid-year-population-estimates-northern-ireland-and-estimates-population-aged-85)

`historical_calibration_result.yaml` records the bounded causal parameters,
fit years, untouched holdout, tolerances, searched and accepted candidate
counts, seed dispersion, and independent validation. Aggregate components are
expected rates, not checkpoint corrections, and different seeds retain
stochastic variation. Newborn transmission from 2011 is anchored to:

- [NISRA Census 2021 commissioned table CT0156](https://www.nisra.gov.uk/publications/ct0156-religion-or-religion-brought-combination-family)

The four-category child matrix is a reduced-form, one-sampled-parent estimate
derived from family combinations. Adult movement to None represents effective
change in Census response category and is not an observed change of upbringing.

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

The current synthetic baseline also preserves the Census 2021 relationship
between broad age and community background from table MS-B31. In particular,
23.36% of the Protestant-and-other-Christian-background population was aged
65+, compared with 14.22% of the Catholic-background population. Five-year age
detail within each published broad band follows MS-A02. This matters because
the age-specific mortality schedule must operate on the observed older
Protestant-background distribution rather than independent age assignments.

- [NISRA Census 2021 table MS-B31](https://www.nisra.gov.uk/publications/census-2021-main-statistics-northern-ireland-supplemental)

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

External arrivals in this variant use
`ni_external_arrivals_lgd_2021_by_religion.csv`, extracted from Census 2021
ODMG20NI-UK and ODMG20NI-ROI. The 27,257 people represented were living in GB,
the Republic of Ireland, or elsewhere outside the UK one year before Census
day and living in an NI LGD on Census day. Each simulated year's official
NI-wide inflow (or observed net addition where separate flows are unavailable)
is allocated using that observed joint origin, destination-LGD and
current-religion distribution. ROI is separated from the UK table's aggregate
Outside UK category using the dedicated ROI table.

This is an arrival-composition baseline, not evidence that the 2021 pattern
will remain unchanged. Current religion is again a proxy for community
background. Equivalent destination-LGD-by-religion evidence is not available
for people leaving NI, so emigration retains the conservative estimated
community differentials above and remains spatially proportional within each
community cohort.

- [Census 2021 migration origin-destination tables (UK)](https://www.nisra.gov.uk/publications/census-2021-origin-destination-migration-tables-uk)
- [Census 2021 migration origin-destination tables (ROI)](https://www.nisra.gov.uk/publications/census-2021-origin-destination-migration-tables-roi)

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
people.

`ni_internal_migration_lgd_2021_by_religion.csv` adds the mover composition
published in ODMG20NI-UK. The five published current-religion categories are
mapped to the model's four groups: Catholic and Protestant/other Christian map
directly, Other Religions maps to Other, and No Religion plus Religion Not
Stated map to None. Disclosure treatment leaves the religion table 15 people
short of ODMG01; each origin-destination set is proportionally controlled with
largest remainders to its authoritative ODMG01 total. Rates divide each
controlled flow by the corresponding source-LGD Census 2021
community-background population.

ODMG20 records current religion, not “religion or religion brought up in”. Its
use for modelled community background is therefore a documented proxy. It is,
however, materially better supported than assuming movers have the average
community composition of their entire source LGD—the previous assumption that
created artificial Protestant inflows into western districts.

- [Census 2021 origin–destination migration tables](https://www.nisra.gov.uk/publications/census-2021-origin-destination-migration-tables-uk)
- [Census 2021 LGD population table](https://build.nisra.gov.uk/en/custom/data?d=PEOPLE&v=LGD14)
- [NISRA migration methodology](https://datavis.nisra.gov.uk/population/methodology_report.html)

These are observed one-year Census flows, not a forecast. The current model
holds their per-origin-population rates constant after 2021 as a documented
estimate. Census 2021 took place during pandemic restrictions, and NISRA notes
that migration outputs may have been affected. The simulation selects all
origin–destination moves from the pre-move population and applies them
simultaneously, preventing rule order from moving a person twice.

## Border-poll scenarios

The primary political calibration uses LucidTalk's Winter 2025 weighted NI
Tracker, including its published community cross-breaks. Its NI-wide result was
41% united Ireland, 48% remain in the UK, 10% unsure but intending to vote, and
1% would not vote or spoil. Custom baselines are entered across the first three
categories and must total 100%; iterative proportional fitting shifts the
LucidTalk subgroup odds until the simulated NI-wide adult population matches
the custom values. This preserves relative community and LGD differences and
does not turn the custom inputs into flat area values. It remains a user-defined
scenario and inherits LucidTalk's sampling interval rather than representing a
new poll.

The dropdown also includes the highest and lowest comparable LucidTalk
immediate border-poll results in the five years to August 2026. August 2021 is
the high case (42% unite, 49% remain, 9% undecided); February 2024 is the low
case (39% unite, 49% remain, 11% undecided and 1% would not vote/spoil). The
February 2024 scenario uses that poll's published community cross-breaks. An
equivalent August 2021 cross-break workbook was not available from LucidTalk's
current archive, so that scenario transparently uses the Winter 2025 community
pattern raked to the August 2021 NI-wide result.

All built-in LucidTalk options are raked to their published overall totals
against the fixed current reference population. Subsequent movement therefore
comes from simulated demographic change rather than recalibration each year.
The decided-voter headline divides Unite and Remain by their combined share;
it does not assign individual undecided respondents.

- [LucidTalk Winter 2025 NI Tracker and data tables](https://www.lucidtalk.co.uk/news/lt-ni-tracker-poll-winter-2025/)
- [LucidTalk Winter 2024 NI Tracker and data tables](https://www.lucidtalk.co.uk/news/lucidtalk-ni-tracker-poll-winter-2024/)
- [August 2021 LucidTalk result and fieldwork](https://www.theguardian.com/politics/2021/aug/29/majority-of-northern-irish-voters-want-vote-on-staying-uk)

## Assumptions not yet replaced

- education is conditionally sampled from hand-authored age assumptions.
- historical mortality by age, community-specific component multipliers, and
  internal migration rates remain bounded or hand-authored assumptions even
  where aggregate annual totals are observed.
- voting propensities remain scenario parameters, not observed vote-intention
  estimates.
