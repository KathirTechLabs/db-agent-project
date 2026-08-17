from oracle_rule_fetcher.config import ParentConfig, RuleConfig, RuleRegistryEntry


def select_enabled(parent: ParentConfig) -> list[RuleRegistryEntry]:
    return [rule for rule in parent.rules if rule.enabled]


def effective_limit(rule: RuleConfig, global_limit: int) -> int:
    return rule.limit if rule.limit is not None else global_limit
