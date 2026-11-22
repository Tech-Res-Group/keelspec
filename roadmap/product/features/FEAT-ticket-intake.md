---
id: FEAT-ticket-intake
title: Intake that turns GitHub Issues, Linear or Jira tickets into draft feature files
status: idea
outcome: OUT-agent-changes-pass-risk-review
customer_impact: medium
data: internal
reversible: true
acceptance:
  - "`keelspec intake <issue URL | LIN-123 | JIRA-KEY>` writes product/features/FEAT-<slug>.md with status `idea`, a link back to the ticket, and acceptance criteria as bare strings, and the result passes `keelspec validate`."
  - "Field mapping lives in product.config.yaml (an `intake:` block naming the target type and fields), so intake never writes a field the project's schema does not declare."
  - "Without `--draft`, intake is deterministic and sends ticket content to no model."
  - "With `--draft`, a model proposes acceptance criteria and writes what it could not determine as ST-02 questions in .keelspec/disambiguations/, rather than inventing answers. It never fills in an approval."
  - "The feature file is the source of truth. Each imported file records its ticket key and the ticket revision it was last synced from."
  - "`keelspec intake --sync` detects every ticket whose revision has moved and turns each change into a proposed edit to the feature file, on a branch and pull request. It never writes to the default branch. The edit meets `keelspec validate` and a human merge like any other change."
  - "If the ticket and the file have both changed since the last sync, the sync shows both sides and stops for a person. It never picks a winner."
  - "Sync can run from a scheduled CI job or from a tracker webhook, and the result is identical either way."
  - "Write-back to the ticket is limited to a link to the feature file and its status. The ticket never overrides the file."
  - "Credentials come from the environment only (GH_TOKEN, LINEAR_API_KEY, JIRA_*), and no new runtime dependency is added."
---
**Already exists.** The `features` type with a required `acceptance` list, where bare
strings are allowed while drafting (PAC-900 fires only at `shipped`). `status: idea`.
ST-01 Understand reads the graph. ST-02 Disambiguate already has the questions file
and named approvals by role. The MCP server exposes the graph read-only, so an agent
can find valid ids instead of inventing them.

**Genuinely new.** Everything about tickets: the command, the three source clients
(start with GitHub Issues, then Linear, then Jira), the config mapping, re-import
behaviour, and the optional drafting step. Nothing in `keelspec/` touches an issue
tracker today.

**Decided (2026-11-16).** The feature file is the source of truth. A ticket is an input
channel: every change to it must reach the file, but only as a proposed change that
passes the gate and a human merge. That is product-as-code applied to intake, because
nothing becomes intent without a reviewed commit.
