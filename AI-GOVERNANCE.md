# AI governance

What `keelspec orchestrate` does with models and data, what it records, and what it
leaves to your organisation's policy. `build`, `validate`, `evidence`, `lsp` and `mcp`
call no model and send nothing anywhere. This page is about the agent-built line only.

## Models

| | where it is set | default |
|---|---|---|
| Model per station | `ROSTER` in [`keelspec/orchestration.py`](keelspec/orchestration.py) | `claude-haiku-4-5` for ST-01 Understand; `claude-opus-5` for every other agent station |
| Endpoint | the runner: `ClaudeRunner` (Anthropic API), or `OpenAIRunner` / `OpenAICodingRunner` pointed at any OpenAI-compatible `base_url`, such as an internal gateway | Anthropic API |
| Cross-provider critic | `--cross-provider`, `OPENROUTER_MODEL` | off; `openai/gpt-4o` via OpenRouter when on |
| External builder at ST-04 | `--builder claude-code` or `--builder codex` | off; the built-in Develop station |

**Change control.** Station models are code. Changing one is a reviewed commit, the
same as any other change to the line. Routing through your own gateway (`base_url`
plus the `x-fife-concept` station header) moves model choice into that gateway's
config, where your own approval process can own it.

**Inventory.** The table above is the line's whole model surface. Your approved
model and tool inventory is your organisation's to keep. Point the runners at a
gateway that enforces it.

## Data

| what leaves the machine | to whom | when |
|---|---|---|
| Station prompts: the feature, its linked artifacts, other artifact ids, the design, diff summaries, test notes | the configured endpoint | every agent station |
| File contents ST-04 Develop chooses to read inside the project root | the configured endpoint | Develop and repair |
| Diff summary, test names and coverage notes, **without** product context | OpenRouter | only with `--cross-provider` and `OPENROUTER_API_KEY` |

The cross-provider critic is a third party, so it gets the minimum. If your data
classification does not allow source-derived text to leave for OpenRouter, do not
enable it, or point `CrossProviderLens` at an approved endpoint.

**External builders.** With `--builder`, the agent's own CLI runs in a temporary git
worktree of your repository at `HEAD`, and sends whatever that agent sends to its
vendor: the station prompt, plus any file in the worktree it chooses to read. That is
Anthropic for `claude-code` and OpenAI for `codex`, under the account or key that CLI
is logged in with. KeelSpec never reads, stores or passes those credentials. Point the
CLI at your own gateway through its own configuration if your policy requires it.
Uncommitted files are not in the worktree, and nothing outside it is offered.

The built-in Develop station's tools are confined to the project root. Absolute paths, `..` and symlink
escapes are refused. There is no shell, no network and no delete.

**Residency and retention at the provider** are set by your provider agreement and
gateway, not by KeelSpec.

## What is recorded locally

| file | contents | keep it? |
|---|---|---|
| `.keelspec/runs/<feature>-<stamp>.json` | every station's structured output, every verdict, triage, risk tier, approvals, timings | Your call. It is the audit trail of what the line did. |
| `.keelspec/runs/<feature>-<stamp>.patch` | the change an external builder made, as a git patch | Keep it with its run record. It is what the critics judged. |
| `.keelspec/disambiguations/<feature>.json` | the human gate: questions, answers, and named approvals by role | Commit it. The commit is the approver's signature. |

Neither file stores prompts or raw model responses beyond the structured results.

## Human accountability

- **Before Design**, open questions stop the line, and a risk tier's `approvers` (by
  role) must each accept the spec. An autonomous run cannot waive a required approver.
- **On refutation**, triage decides whether the fault is one a retry can fix. If it
  is a requirement, design, dependency, environment, model or business-decision
  problem, it goes to a person.
- **Nothing merges.** The line's terminal state is a report. `validate` is a
  deterministic gate, and a person merges.

A second model is a second opinion, not a substitute for domain expertise, an
accountable approver or business validation. The line is built so that it never has
to pretend otherwise.

## Evaluation

The five Verify lenses default to *refuted* unless convinced, and each targets a
class of omission: wrong behaviour, vacuous tests, security, failure semantics, and
business-process integrity. `keelspec runs` reports refutation rates by lens and
triage causes over time. A drift in those numbers after a model change is the signal
to look.

## Not covered here

These are your organisation's policy, and KeelSpec does not pretend to set them:
- an approved model and tool inventory
- data classification per model
- retention of prompts at the provider
- AI incident reporting
- periodic revalidation of the toolset
