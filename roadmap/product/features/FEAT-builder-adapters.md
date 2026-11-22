---
id: FEAT-builder-adapters
title: Ready-made builder adapters at ST-04 Develop (Claude Code, Codex, Devin, Copilot coding agent)
status: building
outcome: OUT-agent-changes-pass-risk-review
nfrs: [NFR-external-builder-contained]
customer_impact: high
data: financial
reversible: true
acceptance:
  - "`keelspec orchestrate FEAT-x --builder claude-code` (and `codex`) runs ST-04 through that agent's headless CLI in an isolated git worktree, and every other station is unchanged."
  - "The Develop result (files_changed, diff_summary) is computed from the worktree's actual git diff, never from the agent's own report of what it did."
  - "A diff that touches product_dir, the committed bundle, .keelspec/ or CI config fails Develop (NFR-external-builder-contained)."
  - "Devin and Copilot coding agent run as asynchronous adapters: open the task, wait with a timeout for the branch or PR, fetch its diff, and abstain cleanly on timeout."
  - "The run record names the builder, its version and the worktree commit, so `keelspec runs` can split first-pass rate by builder."
  - "AI-GOVERNANCE.md's data table lists, per adapter, what leaves the machine and to whom."
  - "No new runtime dependency: adapters shell out to the agent's own CLI or call its HTTP API with the standard library, matching CrossProviderLens."
---
**Already exists.** The `Runner` protocol (`keelspec/orchestration.py`, "the runner
seam") already lets a project replace any station. `CodingRunner` and
`OpenAICodingRunner` (`keelspec/coding.py`) run Develop as a bounded tool loop through
a `Sandbox`. `DEVELOP_SCHEMA` is the contract Develop must return. `StubRunner` and
`--dry-run` give an offline test path. `--write` is already opt-in.

**Genuinely new.** (1) A `--builder` choice in the CLI, which today always wires
`CodingRunner`. (2) Worktree isolation plus diff-based accounting, because external
agents bring their own shell, so the `Sandbox` guarantee no longer holds (see the NFR).
(3) Asynchronous, PR-based adapters for Devin and Copilot, which do not fit a
synchronous `run()` call. (4) Builder identity on the run record.

**Order.** Claude Code and Codex first: both have local headless CLIs, so they fit
`run()` directly. Devin and Copilot second, once the async shape is settled.

**Decided (2026-11-16).** KeelSpec never handles credentials. Each adapter runs the
agent's own CLI, which authenticates however it is configured: a personal login on a
laptop, or an API key or service account in CI. The run record names the builder.

**Built (unreleased).** Phase 1: `--builder claude-code` and `--builder codex`
(`keelspec/builders.py`, `tests/test_builders.py`). When the builder and critics share
a vendor, the run record says so. A risk tier can make it a hard rule with `independent_critic: true`.
Devin and Copilot (async, PR-based) are phase 2.
