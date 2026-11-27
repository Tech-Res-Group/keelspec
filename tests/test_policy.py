"""v2 M6: the policy engine. Spec 5.3 rules 1-7, each with a test, and explain == run."""
from __future__ import annotations

import json
import pathlib

import pytest

from keelspec import mcp
from keelspec.config import load_config
from keelspec.engine import load
from keelspec.index import ProductIndex
from keelspec.runtime.policy import (
    AgentPolicies,
    PolicyDecision,
    Unevaluable,
    condition_holds,
    evaluate,
    explain,
    offered_operations,
)
from keelspec.runtime.redact import redact

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "payments-exceptions"
AGENT = "AGENT-payment-exceptions"


@pytest.fixture(scope="module")
def bundle():
    return load(load_config(EXAMPLE / "product.config.yaml"), EXAMPLE)


@pytest.fixture(scope="module")
def ap(bundle):
    return AgentPolicies.from_bundle(bundle, AGENT)


def synthetic(*policies, ops=(("op", "read"),), data_classes=("pii",)):
    """An agent with one tool and the given policies, for table-driven rules."""
    tool = {"id": "TOOL-t", "data_classes": list(data_classes),
            "operations": [{"name": n, "side_effects": s} for n, s in ops]}
    pols = [{"id": f"POL-{i}", **p} for i, p in enumerate(policies)]
    agent = {"id": "AGENT-s", "tools": ["TOOL-t"], "policies": [p["id"] for p in pols]}
    return AgentPolicies.from_bundle({"agents": [agent], "tools": [tool], "policies": pols},
                                     "AGENT-s")


ANY = {"tool": "TOOL-t"}


# ── rule 1: only matching policies are collected ─────────────────────────────
def test_rule1_a_policy_whose_match_does_not_fit_is_ignored():
    ap = synthetic({"effect": "allow", "match": ANY},
                   {"effect": "deny", "match": {"tool": "TOOL-t", "operation": "other"}},
                   ops=(("op", "read"), ("other", "write")))
    assert evaluate(ap, "TOOL-t", "op").effect == "allow"
    assert evaluate(ap, "TOOL-t", "other").effect == "deny"


# ── rule 2: when conditions, ANDed, no expressions ───────────────────────────
@pytest.mark.parametrize("cond, args, holds", [
    ({"arg": "a", "op": "==", "value": 1}, {"a": 1}, True),
    ({"arg": "a", "op": "!=", "value": 1}, {"a": 2}, True),
    ({"arg": "a", "op": ">", "value": 1}, {"a": 2}, True),
    ({"arg": "a", "op": ">=", "value": 2}, {"a": 2}, True),
    ({"arg": "a", "op": "<", "value": 1}, {"a": 2}, False),
    ({"arg": "a", "op": "<=", "value": 2}, {"a": 2}, True),
    ({"arg": "c", "op": "in", "value": ["EUR", "GBP"]}, {"c": "EUR"}, True),
    ({"arg": "c", "op": "not_in", "value": ["EUR"]}, {"c": "USD"}, True),
    ({"arg": "r", "op": "matches", "value": "^INV-\\d+$"}, {"r": "INV-22"}, True),
    ({"arg": "x", "op": "exists"}, {"x": None}, True),
    ({"arg": "x", "op": "exists", "value": False}, {}, True),
    ({"arg": "p.amount_minor", "op": ">", "value": 0}, {"p": {"amount_minor": 5}}, True),
    ({"arg": "items.1", "op": "==", "value": "b"}, {"items": ["a", "b"]}, True),
])
def test_rule2_each_operator(cond, args, holds):
    assert condition_holds(cond, args) is holds


@pytest.mark.parametrize("cond, args", [
    ({"arg": "a", "op": ">", "value": 0}, {}),                 # missing
    ({"arg": "a", "op": ">", "value": 0}, {"a": "9"}),         # not a number
    ({"arg": "a", "op": ">", "value": 0}, {"a": True}),        # a bool is not a number
    ({"arg": "a", "op": "in", "value": 3}, {"a": 1}),          # value not a container
    ({"arg": "a", "op": "~=", "value": 0}, {"a": 1}),          # unknown op
    ({"op": "==", "value": 0}, {"a": 1}),                      # no path
])
def test_rule2_an_undecidable_condition_raises(cond, args):
    with pytest.raises(Unevaluable):
        condition_holds(cond, args)


def test_rule2_conditions_in_a_list_are_anded():
    when = [{"arg": "a", "op": ">", "value": 0}, {"arg": "c", "op": "==", "value": "EUR"}]
    ap = synthetic({"effect": "allow", "match": ANY, "when": when})
    assert evaluate(ap, "TOOL-t", "op", {"a": 1, "c": "EUR"}).effect == "allow"
    assert evaluate(ap, "TOOL-t", "op", {"a": 1, "c": "USD"}).effect == "deny"


def test_rule2_fail_closed_restrictive_applies_permissive_does_not():
    ap = synthetic({"effect": "allow", "match": ANY},
                   {"effect": "deny", "match": ANY, "when": {"arg": "amt", "op": ">", "value": 100}})
    # A deny that cannot be decided applies: doubt never widens what the agent may do.
    d = evaluate(ap, "TOOL-t", "op", {"amt": "lots"})
    assert d.effect == "deny" and "failing closed" in d.reason
    ap = synthetic({"effect": "allow", "match": ANY, "when": {"arg": "amt", "op": "<", "value": 100}})
    assert evaluate(ap, "TOOL-t", "op", {}).effect == "deny"       # an undecidable allow does not


# ── rule 3: precedence, table-driven ─────────────────────────────────────────
@pytest.mark.parametrize("effects, expected", [
    (["allow", "deny"], "deny"),
    (["allow", "require_approval", "deny", "redact"], "deny"),
    (["allow", "require_approval"], "require_approval"),
    (["require_approval", "redact"], "require_approval"),
    (["allow", "redact"], "redact"),
    (["allow"], "allow"),
])
def test_rule3_precedence(effects, expected):
    ap = synthetic(*({"effect": e, "match": ANY} for e in effects))
    assert evaluate(ap, "TOOL-t", "op").effect == expected


# ── rule 4: default deny; redact is not permission ───────────────────────────
def test_rule4_no_matching_policy_is_denied_with_no_policy():
    d = evaluate(synthetic(), "TOOL-t", "op")
    assert d.effect == "deny" and d.reason.startswith("no_policy") and not d.permitted


def test_rule4_a_redact_policy_alone_does_not_permit_the_call():
    d = evaluate(synthetic({"effect": "redact", "match": {"data_classes": ["pii"]}}), "TOOL-t", "op")
    assert d.effect == "deny" and "redact is not permission" in d.reason


# ── rule 5: undeclared tools and operations ──────────────────────────────────
def test_rule5_only_declared_operations_are_offered(ap):
    offered = offered_operations(ap)
    assert ("TOOL-case-management", "release_funds") in offered     # declared, then denied
    assert all(t in ap.agent["tools"] for t, _ in offered)


def test_rule5_an_undeclared_call_is_denied_even_if_a_policy_would_allow_it(ap):
    for tool, op in (("TOOL-case-management", "delete_case"), ("TOOL-unknown", "get")):
        d = evaluate(ap, tool, op)
        assert d.effect == "deny" and d.reason.startswith("not_declared")


# ── rule 6: every evaluation is a PolicyDecision ─────────────────────────────
def test_rule6_decisions_carry_effect_policies_and_reason(ap):
    d = evaluate(ap, "TOOL-case-management", "release_funds", {"amount_minor": 1})
    assert isinstance(d, PolicyDecision)
    assert (d.effect, d.policy_ids) == ("deny", ("POL-no-funds-movement",))
    assert json.loads(json.dumps(d.to_dict()))["reason"]


# ── rule 7: redaction of results ─────────────────────────────────────────────
def test_rule7_reads_on_a_pii_tool_are_allowed_and_masked(ap, bundle):
    d = evaluate(ap, "TOOL-payments-ledger", "get_payment", {"end_to_end_id": "E2E-77F"})
    assert d.effect == "redact" and d.redact_classes == ("pii",)
    tool = ap.tools["TOOL-payments-ledger"]
    result = {"end_to_end_id": "E2E-77F", "amount_minor": 125000,
              "debtor": {"name": "Ada Lovelace", "account": "DE89370400440532013000"}}
    masked = redact(result, tool, "get_payment", d.redact_classes)
    assert masked["debtor"] == {"name": "[REDACTED:pii]", "account": "[REDACTED:pii]"}
    assert masked["amount_minor"] == 125000 and result["debtor"]["name"] == "Ada Lovelace"


def test_rule7_wildcards_reach_into_lists():
    tool = {"id": "TOOL-t", "operations": [{"name": "op", "fields": {"rows.*.iban": "pii"}}]}
    out = redact({"rows": [{"iban": "A", "n": 1}, {"iban": "B", "n": 2}]}, tool, "op", ["pii"])
    assert out == {"rows": [{"iban": "[REDACTED:pii]", "n": 1}, {"iban": "[REDACTED:pii]", "n": 2}]}


def test_rule7_an_operation_that_tags_nothing_is_withheld_whole():
    tool = {"id": "TOOL-t", "operations": [{"name": "op"}]}
    out = redact({"name": "Ada"}, tool, "op", ["pii"])
    assert out["redacted"] is True and "Ada" not in json.dumps(out)


# ── the example's own decisions ──────────────────────────────────────────────
@pytest.mark.parametrize("tool, op, args, effect", [
    ("TOOL-case-management", "release_funds", {}, "deny"),
    ("TOOL-case-management", "propose_repair", {"amount_minor": 500}, "require_approval"),
    ("TOOL-case-management", "propose_repair", {"amount_minor": 0}, "deny"),     # no allow
    ("TOOL-case-management", "add_comment", {"text": "AC04"}, "redact"),         # pii tool
    ("TOOL-iso20022-parser", "explain_status", {"code": "AC04"}, "allow"),
])
def test_the_example_agent(ap, tool, op, args, effect):
    assert evaluate(ap, tool, op, args).effect == effect


def test_require_approval_names_its_approvers(ap):
    d = evaluate(ap, "TOOL-case-management", "propose_repair", {"amount_minor": 1})
    assert d.approvers == ("payments-ops-lead",) and not d.permitted


# ── explain == run, on every surface ─────────────────────────────────────────
CALLS = [("TOOL-case-management", "release_funds", {}),
         ("TOOL-case-management", "propose_repair", {"amount_minor": 500}),
         ("TOOL-payments-ledger", "get_payment", {}),
         ("TOOL-case-management", "teleport", {})]


@pytest.mark.parametrize("tool, op, args", CALLS)
def test_explain_matches_the_runtime_decision(bundle, ap, tool, op, args):
    assert explain(bundle, AGENT, tool, op, args)["decision"] == evaluate(ap, tool, op, args).to_dict()


@pytest.mark.parametrize("tool, op, args", CALLS)
def test_mcp_policy_explain_matches_the_runtime_decision(ap, tool, op, args):
    idx = ProductIndex.build(load_config(EXAMPLE / "product.config.yaml"), EXAMPLE)
    out = mcp.policy_explain(idx, AGENT, tool, op, args)
    assert out["decision"] == evaluate(ap, tool, op, args).to_dict()


def test_cli_policy_explain(capsys):
    from keelspec.cli import main
    assert main(["-C", str(EXAMPLE), "policy", "explain", AGENT, "TOOL-case-management",
                 "release_funds", "{}"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"]["effect"] == "deny"
    assert out["decision"]["policy_ids"] == ["POL-no-funds-movement"]
    assert out["side_effects"] == "money"
    assert main(["-C", str(EXAMPLE), "policy", "explain", AGENT, "TOOL-x", "op", "{bad"]) == 2
    assert main(["-C", str(EXAMPLE), "policy", "explain", "AGENT-nobody", "TOOL-x", "op"]) == 2


def test_mcp_agent_card_resolves_the_agent():
    idx = ProductIndex.build(load_config(EXAMPLE / "product.config.yaml"), EXAMPLE)
    card = mcp.agent_card(idx, AGENT)
    assert card["instructions"].startswith("## Instructions")
    assert {g["id"] for g in card["grounding"]} == {
        "BR-idempotent", "CON-money-is-integer-minor-units", "TERM-return-reason"}
    ops = {t["id"]: [o["name"] for o in t["operations"]] for t in card["tools"]}
    assert "release_funds" in ops["TOOL-case-management"]
    assert mcp.agent_card(idx, "AGENT-none") == {"error": "no agent 'AGENT-none'"}
    assert mcp.policy_explain(idx, "AGENT-none", "TOOL-x", "op")["error"]


def test_the_policy_engine_needs_no_optional_dependency():
    import keelspec.runtime.policy as policy
    import keelspec.runtime.redact as red
    for mod in (policy, red):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "import httpx" not in src and "import mcp" not in src
