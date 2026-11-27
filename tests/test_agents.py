"""v2 M5: agent artifact types, multi-target references, PAC-070..077 in validate.

The example project (examples/payments-exceptions/) is the fixture: it must validate
clean, and a copy broken in one place must raise exactly the code for that place.
"""
from __future__ import annotations

import pathlib
import re
import shutil

import pytest
import yaml

from keelspec import agents, lsp, mcp
from keelspec.config import Config, load_config
from keelspec.diagnostics import CODES
from keelspec.engine import build, parse_frontmatter, validate
from keelspec.index import ProductIndex

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "payments-exceptions"


def _codes(report) -> list[str]:
    return sorted(d.code for d in report.diagnostics)


@pytest.fixture()
def example(tmp_path) -> pathlib.Path:
    root = tmp_path / "ex"
    shutil.copytree(EXAMPLE, root)
    return root


def _check(root: pathlib.Path):
    """Rebuild, then validate, so a deliberate break is not also reported as PAC-060."""
    cfg = load_config(root / "product.config.yaml")
    build(cfg, root)
    return validate(cfg, root)


def _edit(root: pathlib.Path, rel: str, **fields):
    path = root / "product" / rel
    meta, body = parse_frontmatter(path)
    for key, value in fields.items():
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
    path.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n" + body + "\n",
                    encoding="utf-8")


AGENT = "agents/AGENT-payment-exceptions.md"


# ── the example ──────────────────────────────────────────────────────────────
def test_the_example_validates_clean_with_its_committed_bundle():
    cfg = load_config(EXAMPLE / "product.config.yaml")
    report = validate(cfg, EXAMPLE)          # no rebuild: the committed bundle must be current
    assert report.diagnostics == []


def test_removing_the_repair_approval_breaks_the_money_path_rule(example):
    """The demo step: delete POL-repair-needs-approval and validate."""
    (example / "product/policies/POL-repair-needs-approval.md").unlink()
    codes = _codes(_check(example))
    assert "PAC-074" in codes                 # propose_repair moves money, unguarded
    assert "PAC-020" in codes                 # and the agent still links the deleted policy


# ── one break, one code ──────────────────────────────────────────────────────
def test_pac070_policy_names_an_operation_its_tool_does_not_declare(example):
    _edit(example, "policies/POL-repair-needs-approval.md",
          match={"tool": "TOOL-case-management", "operation": "propose_repairs"})
    assert "PAC-070" in _codes(_check(example))


def test_pac070_operation_without_a_tool_must_exist_on_some_agent_tool(example):
    _edit(example, "policies/POL-allow-case-comments.md", match={"operation": "shred_case"})
    assert "PAC-070" in _codes(_check(example))


def test_pac071_an_operation_nothing_permits_is_a_warning(example):
    meta, _ = parse_frontmatter(example / "product" / AGENT)
    _edit(example, AGENT, policies=[p for p in meta["policies"] if p != "POL-allow-case-comments"])
    report = _check(example)
    found = [d for d in report.diagnostics if d.code == "PAC-071"]
    assert [d.value for d in found] == ["TOOL-case-management.add_comment"]
    assert found[0].severity == "warning" and report.errors == []


def test_pac071_a_redact_policy_alone_is_not_permission(example):
    _edit(example, AGENT, policies=["POL-pii-redaction", "POL-no-funds-movement",
                                    "POL-repair-needs-approval"])
    values = {d.value for d in _check(example).diagnostics if d.code == "PAC-071"}
    assert "TOOL-payments-ledger.get_payment" in values


def test_pac071_is_silent_for_an_operation_that_is_always_denied(example):
    values = {d.value for d in _check(example).diagnostics if d.code == "PAC-071"}
    assert "TOOL-case-management.release_funds" not in values


@pytest.mark.parametrize("when, needle", [
    ({"arg": "amount_minor", "op": "~=", "value": 0}, "op '~='"),
    ({"arg": "amount minor", "op": ">", "value": 0}, "not a dotted path"),
    ({"arg": "amount_minor", "op": ">", "value": "zero"}, "must be a number"),
    ({"arg": "currency", "op": "in", "value": "EUR"}, "must be a list"),
    ({"arg": "ref", "op": "matches", "value": "("}, "not a valid pattern"),
    ({"arg": "ref", "op": "=="}, "needs a value"),
    ({"arg": "ref", "op": "exists", "value": "yes"}, "true or false"),
    ({"arg": "ref", "op": "==", "value": 1, "unless": 2}, "unknown key"),
    ("amount_minor > 0", "a condition or a list"),
    ([{"arg": "a", "op": "==", "value": 1}, "b"], "when[1] is not a mapping"),
])
def test_pac072_malformed_when(example, when, needle):
    _edit(example, "policies/POL-repair-needs-approval.md", when=when)
    found = [d for d in _check(example).diagnostics if d.code == "PAC-072"]
    assert found and any(needle in d.message for d in found)


def test_pac072_a_match_with_an_unknown_key_fails_closed(example):
    _edit(example, "policies/POL-allow-case-comments.md",
          match={"tool": "TOOL-case-management", "operaton": "add_comment"})
    msgs = [d.message for d in _check(example).diagnostics if d.code == "PAC-072"]
    assert any("unknown key" in m for m in msgs)


def test_pac074_needs_a_guard_only_for_high_criticality(example):
    meta, _ = parse_frontmatter(example / "product" / AGENT)
    unguarded = [p for p in meta["policies"] if p != "POL-repair-needs-approval"]
    _edit(example, AGENT, policies=unguarded)
    assert "PAC-074" in _codes(_check(example))
    _edit(example, AGENT, criticality="medium")
    assert "PAC-074" not in _codes(_check(example))


def test_pac075_an_agent_with_no_scenarios_warns(example):
    (example / "product/agents/AGENT-quiet.md").write_text(
        "---\nid: AGENT-quiet\ntitle: Q\npurpose: p\nconcept: general.assist\n"
        "criticality: low\ntools: [TOOL-iso20022-parser]\npolicies: [POL-allow-reads]\n---\n",
        encoding="utf-8")
    report = _check(example)
    found = [d for d in report.diagnostics if d.code == "PAC-075"]
    assert len(found) == 1 and found[0].severity == "warning"
    assert report.errors == []


@pytest.mark.parametrize("field, value, needle", [
    ("fixtures", {"TOOL-case-management.delete_case": {}}, "cannot call"),
    ("fixtures", {"TOOL-unknown.get": {}}, "cannot call"),
    ("fixtures", {"no-dot-here": {}}, "is not TOOL-id.operation"),
    ("expect", {"must_call": ["TOOL-case-management.archive"]}, "expect.must_call"),
])
def test_pac077_a_scenario_names_an_operation_its_agent_cannot_call(example, field, value, needle):
    _edit(example, "scenarios/SCN-ac04-closed-account.md", **{field: value})
    found = [d for d in _check(example).diagnostics if d.code == "PAC-077"]
    assert found and any(needle in d.message for d in found)


def test_an_operation_side_effect_outside_the_enum_is_pac030(example):
    _edit(example, "tools/TOOL-iso20022-parser.md",
          operations=[{"name": "explain_status", "side_effects": "teleport"},
                      {"name": "parse_message", "side_effects": "none"}])
    assert "PAC-030" in _codes(_check(example))


# ── presets ──────────────────────────────────────────────────────────────────
def test_presets_expand_into_the_four_types():
    cfg = Config.model_validate({"presets": ["agents"], "types": []})
    assert [t.name for t in cfg.types] == ["agents", "tools", "policies", "scenarios"]
    assert cfg.type_by_name("agents").enums["criticality"] == ["low", "medium", "high"]


def test_a_project_without_presets_sees_no_change(tmp_path):
    cfg = Config.model_validate({"types": [{"name": "agents", "dir": "agents"}]})
    assert cfg.presets == [] and not agents.enabled(cfg)


def test_an_unknown_preset_is_a_config_error():
    with pytest.raises(ValueError, match="unknown preset"):
        Config.model_validate({"presets": ["robots"], "types": []})


def test_a_type_declared_twice_is_a_config_error_not_an_override():
    with pytest.raises(ValueError, match="also provided by preset"):
        Config.model_validate({"presets": ["agents"],
                               "types": [{"name": "tools", "dir": "my-tools"}]})


# ── multi-target references ──────────────────────────────────────────────────
def test_grounding_resolves_across_rules_constraints_and_terms(example):
    _edit(example, AGENT, grounding=["BR-idempotent", "TERM-return-reason", "XX-nothing"])
    found = [d for d in _check(example).diagnostics if d.code == "PAC-020"]
    assert [d.value for d in found] == ["XX-nothing"]
    assert "rules, constraints or terms" in found[0].message


def test_a_single_target_reference_is_unchanged():
    cfg = Config.model_validate({"types": [{"name": "a", "dir": "a",
                                            "references": [{"field": "x", "to": "b"}]}]})
    ref = cfg.types[0].references[0]
    assert ref.targets == ["b"] and ref.describe() == "b"


# ── the other surfaces read the same config, with no special code ────────────
def _index():
    return ProductIndex.build(load_config(EXAMPLE / "product.config.yaml"), EXAMPLE)


def test_lsp_completes_tool_ids_inside_an_agents_tools_list():
    rel = "product/" + AGENT
    text = (EXAMPLE / rel).read_text(encoding="utf-8")
    line = next(i for i, ln in enumerate(text.splitlines()) if ln.startswith("tools:"))
    offers = lsp.completions_at(_index(), rel, text, line, len("tools: ["))
    assert [c.label for c in offers] == [
        "TOOL-case-management", "TOOL-iso20022-parser", "TOOL-payments-ledger"]
    assert {c.detail for c in offers} == {"tools"}


def test_lsp_completes_grounding_from_every_target_type():
    rel = "product/" + AGENT
    text = (EXAMPLE / rel).read_text(encoding="utf-8")
    line = next(i for i, ln in enumerate(text.splitlines()) if ln.startswith("grounding:"))
    offers = {c.label: c.detail for c in lsp.completions_at(_index(), rel, text, line, 12)}
    assert offers == {"BR-idempotent": "rules",
                      "CON-money-is-integer-minor-units": "constraints",
                      "TERM-return-reason": "terms"}


def test_mcp_tools_answer_over_the_new_types():
    idx = _index()
    tools = mcp.allowed_values(idx, "agents", "tools")
    assert tools["kind"] == "reference" and "TOOL-payments-ledger" in tools["values"]
    assert mcp.allowed_values(idx, "agents", "grounding")["must_resolve_to"] == \
        "rules | constraints | terms"
    assert {t["type"] for t in mcp.schema(idx)} >= {"agents", "tools", "policies", "scenarios"}
    refs = mcp.references_to(idx, "POL-no-funds-movement")
    assert any(r["source"] == "AGENT-payment-exceptions" for r in refs["referenced_by"])
    assert mcp.validate(idx)["errors"] == 0


# ── shared helpers the runtime will reuse ────────────────────────────────────
LEDGER = {"id": "TOOL-l", "data_classes": ["pii"],
          "operations": [{"name": "get", "side_effects": "read"}, {"name": "pay"}],
          "side_effects": "money"}


@pytest.mark.parametrize("match, op, fits", [
    ({"tool": "TOOL-l"}, "get", True),
    ({"tool": "TOOL-other"}, "get", False),
    ({"operation": "get"}, "get", True),
    ({"side_effects": "read"}, "get", True),
    ({"side_effects": ["none", "read"]}, "pay", False),     # pay inherits the tool's money
    ({"side_effects": "money"}, "pay", True),
    ({"data_classes": ["pii", "x"]}, "get", True),
    ({"data_classes": ["financial"]}, "get", False),
    ({}, "get", False),
])
def test_match_fits(match, op, fits):
    assert agents.match_fits(match, LEDGER, op) is fits


def test_every_v2_code_is_registered_with_its_spec_text():
    assert CODES["PAC-074"].startswith("an agent with criticality: high has no require_approval")
    assert all(re.fullmatch(r"PAC-07\d", c) for c in CODES if c.startswith("PAC-07"))
    assert {f"PAC-07{i}" for i in range(10)} <= set(CODES)
