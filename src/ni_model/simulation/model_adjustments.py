"""Apply user-selected global and community multipliers to model rules."""

RATE_ADJUSTMENTS = {
    "birth_rates": "birth_multiplier",
    "death_rates": "death_multiplier",
    "migration_rates": "migration_multiplier",
    "internal_migration_rates": "relocation_multiplier",
    "integration_rates": "integration_multiplier",
}


def _section_multipliers(adjustments):
    return {
        section: adjustments.get(field, 1.0)
        for section, field in RATE_ADJUSTMENTS.items()
    }


def _community_multipliers(community, field):
    return {
        group.upper(): values.get(field, 1.0) for group, values in community.items()
    }


def _profile_weighted_multiplier(profiles, multipliers):
    total = sum(profile["weight"] for profile in profiles)
    adjusted = sum(
        profile["weight"] * multipliers.get(profile["religious_background"], 1.0)
        for profile in profiles
    )
    return adjusted / total


def _split_rule(rule, multipliers):
    return [
        {
            **rule,
            "rate": rule["rate"] * multiplier,
            "filters": {
                **rule.get("filters", {}),
                "religious_background": group,
            },
        }
        for group, multiplier in multipliers.items()
    ]


def _adjust_rule(rule, section, multipliers, profiles):
    existing_group = rule.get("filters", {}).get("religious_background")
    if existing_group:
        rule["rate"] *= multipliers.get(existing_group, 1.0)
        return [rule]

    unique = set(multipliers.values())
    if len(unique) == 1:
        rule["rate"] *= unique.pop()
        return [rule]

    if section == "migration_rates" and rule["rate"] >= 0 and profiles:
        rule["rate"] *= _profile_weighted_multiplier(profiles, multipliers)
        return [rule]

    return _split_rule(rule, multipliers)


def _adjust_section(config, section, global_multiplier, community):
    rules = config.get(section, [])
    for rule in rules:
        rule["rate"] *= global_multiplier

    multipliers = _community_multipliers(community, RATE_ADJUSTMENTS[section])
    if not multipliers:
        return

    profiles = config.get("immigration_profiles", [])
    config[section] = [
        adjusted
        for rule in rules
        for adjusted in _adjust_rule(rule, section, multipliers, profiles)
    ]
    if section == "migration_rates" and profiles:
        for profile in profiles:
            profile["weight"] *= multipliers.get(profile["religious_background"], 1.0)


def apply_model_adjustments(config, adjustments):
    """Mutate and return a freshly loaded model configuration."""
    multipliers = _section_multipliers(adjustments)
    community = adjustments.get("community") or {}
    for section, multiplier in multipliers.items():
        _adjust_section(config, section, multiplier, community)

    if config.get("annual_demographic_components"):
        config["_component_target_multipliers"] = {
            section: multipliers[section]
            for section in ("birth_rates", "death_rates", "migration_rates")
        }
    if adjustments.get("random_seed") is not None:
        config["random_seed"] = adjustments["random_seed"]
    return config
