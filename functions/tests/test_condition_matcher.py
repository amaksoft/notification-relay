import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from condition_matcher import (  # noqa: E402
    evaluate_condition,
    is_in_grant,
    rule_matches,
    throttle_allows,
)

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "condition_fixtures.json")
with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_condition_fixtures(fixture):
    actual = evaluate_condition(fixture["condition"], fixture["notification"])
    assert actual == fixture["expected"], fixture["name"]


def test_unknown_condition_type_raises():
    with pytest.raises(ValueError):
        evaluate_condition({"type": "NOT_A_REAL_TYPE"}, {})


class TestRuleMatches:
    def test_disabled_rule_never_matches(self):
        rule = {"enabled": False, "condition": {"type": "ALWAYS"}}
        assert rule_matches(rule, {"package": "com.anything"}) is False

    def test_enabled_rule_defers_to_condition(self):
        rule = {"enabled": True, "condition": {"type": "ALWAYS"}}
        assert rule_matches(rule, {"package": "com.anything"}) is True

    def test_enabled_defaults_true_when_absent(self):
        rule = {"condition": {"type": "ALWAYS"}}
        assert rule_matches(rule, {}) is True


class TestThrottleAllows:
    def test_zero_throttle_always_allows(self):
        assert throttle_allows(last_fired_at=1000.0, throttle_seconds=0, now=1000.0) is True

    def test_never_fired_allows(self):
        assert throttle_allows(last_fired_at=None, throttle_seconds=30, now=1000.0) is True

    def test_within_cooldown_blocks(self):
        assert throttle_allows(last_fired_at=1000.0, throttle_seconds=30, now=1010.0) is False

    def test_after_cooldown_allows(self):
        assert throttle_allows(last_fired_at=1000.0, throttle_seconds=30, now=1031.0) is True

    def test_exactly_at_boundary_allows(self):
        assert throttle_allows(last_fired_at=1000.0, throttle_seconds=30, now=1030.0) is True


class TestIsInGrant:
    def test_allow_all(self):
        assert is_in_grant("com.slack", "any_channel", {"allowAll": True}) is True

    def test_no_grants_denies(self):
        assert is_in_grant("com.slack", "dm", {"grants": []}) is False

    def test_none_grants_denies(self):
        assert is_in_grant("com.slack", "dm", None) is False

    def test_whole_package_grant_allows_any_channel(self):
        grants = {"grants": [{"package": "com.slack"}]}
        assert is_in_grant("com.slack", "dm_channel", grants) is True
        assert is_in_grant("com.slack", "alerts_channel", grants) is True

    def test_whole_package_grant_denies_other_package(self):
        grants = {"grants": [{"package": "com.slack"}]}
        assert is_in_grant("com.whatsapp", "dm_channel", grants) is False

    def test_channel_scoped_grant_allows_only_that_channel(self):
        grants = {"grants": [{"package": "com.whatsapp", "channelIds": ["calls_channel"]}]}
        assert is_in_grant("com.whatsapp", "calls_channel", grants) is True
        assert is_in_grant("com.whatsapp", "messages_channel", grants) is False

    def test_channel_scoped_grant_denies_other_package_even_with_same_channel_id(self):
        grants = {"grants": [{"package": "com.whatsapp", "channelIds": ["calls_channel"]}]}
        assert is_in_grant("com.slack", "calls_channel", grants) is False

    def test_multiple_grants_any_can_match(self):
        grants = {
            "grants": [
                {"package": "com.slack"},
                {"package": "com.whatsapp", "channelIds": ["calls_channel"]},
            ]
        }
        assert is_in_grant("com.slack", "anything", grants) is True
        assert is_in_grant("com.whatsapp", "calls_channel", grants) is True
        assert is_in_grant("com.whatsapp", "messages_channel", grants) is False

    # --- Adversarial: the grant gate must hold regardless of what a
    # subscriber's own Condition tree looks like (see plan Architecture
    # overview - the gate is checked BEFORE the Condition ever runs, so
    # these aren't really "attacks" on is_in_grant itself, but they pin
    # down that a condition designed to match everything doesn't matter
    # once combined with the gate in the way ingest.py is meant to use it).
    def test_gate_denies_regardless_of_adversarial_always_true_condition(self):
        grants = {"grants": [{"package": "com.whatsapp", "channelIds": ["calls_channel"]}]}
        adversarial_condition = {
            "type": "OR",
            "conditions": [
                {"type": "ALWAYS"},
                {"type": "ALWAYS", "inverse": True},
            ],
        }
        notification = {"package": "com.slack", "channelId": "dm_channel"}
        # The subscriber's Condition matches everything...
        assert evaluate_condition(adversarial_condition, notification) is True
        # ...but the gate for this (package, channel) still denies it, and
        # per the design the gate is checked first and short-circuits
        # before the Condition is ever evaluated.
        assert is_in_grant(notification["package"], notification["channelId"], grants) is False
