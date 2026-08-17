from oracle_rule_fetcher.config import ParentConfig, RuleConfig, RuleRegistryEntry
from oracle_rule_fetcher.rules import effective_limit, select_enabled


def test_select_enabled_filters_disabled():
    parent = ParentConfig(
        global_limit=50,
        rules=[
            RuleRegistryEntry("a", True, "a.yaml"),
            RuleRegistryEntry("b", False, "b.yaml"),
            RuleRegistryEntry("c", True, "c.yaml"),
        ],
    )
    assert [r.name for r in select_enabled(parent)] == ["a", "c"]


def test_effective_limit_uses_rule_limit_when_set():
    rule = RuleConfig(name="a", sql="SELECT 1 FROM DUAL", limit=10)
    assert effective_limit(rule, global_limit=50) == 10


def test_effective_limit_falls_back_to_global():
    rule = RuleConfig(name="a", sql="SELECT 1 FROM DUAL", limit=None)
    assert effective_limit(rule, global_limit=50) == 50
