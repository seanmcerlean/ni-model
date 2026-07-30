# Step 7a: Query-Based Cohort Calculators - COMPLETED

## Summary
Successfully refactored demographic calculators to use query-based cohorts, enabling demographic-specific rates instead of uniform population-wide rates.

## Key Changes

### DemographicCalculator Base Class
- **Constructor**: Now accepts `rate` and `query_filters` parameters
- **_get_cohort()**: New method that builds SQLAlchemy query based on filters
- **Supported Filters**:
  - `religious_background`: Filter by ReligiousBackground enum
  - `gender`: Filter by Gender enum
  - `age_min` / `age_max`: Filter by age range
  - `location`: Filter by location string
  - `education_level`: Filter by EducationLevel enum

### BirthCalculator
- Applies birth rate only to matching cohort
- New births inherit parent characteristics (religious_background, location)
- Gender randomly assigned, education_level set to PRIMARY

### DeathCalculator
- Applies death rate only to matching cohort
- Random selection from cohort for deaths

### MigrationCalculator
- Applies migration rate only to matching cohort
- Immigrants inherit cohort characteristics when available
- Emigrants selected randomly from cohort

## Example Usage

```python
# Different birth rates by religious background
catholic_births = BirthCalculator(
    session,
    rate=15.0,
    query_filters={'religious_background': ReligiousBackground.CATHOLIC}
)

protestant_births = BirthCalculator(
    session,
    rate=11.0,
    query_filters={'religious_background': ReligiousBackground.PROTESTANT}
)

# Age-specific death rates
elderly_deaths = DeathCalculator(
    session,
    rate=120.0,
    query_filters={'age_min': 80}
)

young_deaths = DeathCalculator(
    session,
    rate=0.5,
    query_filters={'age_max': 20}
)
```

## Test Results
- **15 tests passed** (all green)
- **96% code coverage** for demographic_calculators.py
- **Linting**: All checks pass (black, flake8, isort)

## Test Coverage
Tests validate:
- Basic calculations on entire population
- Cohort-specific calculations (by religion, age, gender)
- Empty cohort handling
- Zero population edge cases
- Sequential demographic changes
- Multiple calculators on different cohorts

## Next Steps
Ready for **Step 7b**: Create ModelDirector to orchestrate multiple calculator instances with model-specific assumptions.
