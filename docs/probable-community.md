# Probable community estimate

`probable_community` is a modelled lineage variable. It does not replace the
Census `religious_background` field and must not be described as a person's
religion, identity, political opinion, or constitutional preference.

## Evidence and calibration

The Census measure is *religion or religion brought up in*. NISRA defines it as
the religion a person belongs to, or the religion in which a person was brought
up when they currently belong to none. Consequently, its `None` category means
that neither question supplied a background; it does not prove that a person
has no culturally relevant family or community lineage.

NISRA table DT-0002 cross-tabulates this measure with eight national-identity
categories. Within each identity category, this model calculates the Catholic,
Protestant, and Other shares of residents whose background is known, then
applies those shares to residents reporting `None` in the same identity category.
Across the 177,361 `None` records this yields an NI-wide estimate of:

- probable Catholic: 67,244 (37.91%)
- probable Protestant: 104,726 (59.05%)
- probable Other: 5,391 (3.04%)

The generated population does not contain national identity. It therefore
uses that NI-wide result as its calibration and varies it conservatively by LGD
using local Catholic-to-Protestant odds after reserving the national 3.04%
Other estimate. The log-odds adjustment is shrunk by
0.65 toward the national result, reducing the risk of treating residential
geography as an individual fact. The intercept is calibrated so that the
LGD-weighted estimate reproduces 37.91% Catholic nationally.

This is consistent with, but deliberately less intrusive than, the Equality
Commission's workplace “residuary method”, which permits evidence including
surname, address, schools and clubs. The simulation only has an LGD-level
address and does not invent surname, school, family, or club records.

## Simulation rules

- Reported Catholic, Protestant, and Other initialise to the same probable
  group.
- Reported None is estimated as Catholic, Protestant, or Other at baseline;
  the probable field never stores None.
- A child uses the existing period-specific background inheritance/mutation
  rule. If the reported outcome is None, probable community inherits from the
  sampled parent. A Catholic, Protestant, or Other outcome updates both fields.
- A transition to reported None preserves probable community. A transition to
  Catholic, Protestant, or Other updates probable community.
- Migration preserves a sampled template's probable community. Profile-based
  arrivals are initialised by the same rules as baseline residents.

## Limitations

This is ecological inference and is uncertain for every individual. National
identity and place correlate with community background but do not determine it.
The estimate must not be used to infer voting behaviour directly. When the UI
uses it for polling, it only selects which published poll community cross-tab
is applied; it is labelled as an estimate and the observed Census view remains
available.

Sources:

- NISRA Census 2021 outputs definitions: https://datavis.nisra.gov.uk/census/census-2021-outputs-definitions.html
- NISRA DT-0002 flexible table: https://build.nisra.gov.uk/en/custom/data?d=PEOPLE&v=NAT_ID_BASIC&v=RELIGION_BELONG_TO_OR_BROUGHT_UP_IN_DVO
- Equality Commission for Northern Ireland, monitoring and the residuary method: https://www.equalityni.org/Employers-Service-Providers/Monitoring/Monitoring-your-workforce
- Doebler and Shuttleworth (2018), religious identification, switching and apostasy: https://livrepository.liverpool.ac.uk/3026520/
