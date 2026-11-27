---
id: FEAT-factory-metrics
title: "Factory metrics: critic rejection rate, spec-drift rate, review load, cost per merged PR"
status: building
outcome: OUT-agent-changes-pass-risk-review
customer_impact: low
data: internal
reversible: true
acceptance:
  - "`keelspec runs --json` reports a rejection rate per lens: blocker or major refutations divided by verdicts cast, with abstentions counted separately."
  - "Spec-drift rate: the share of evidence records in a window whose findings include PAC-060 (or any PAC-0xx), read from records CI keeps under a configured directory."
  - "Review load per feature: needs-human runs, ST-02 questions asked, and approvals required versus given, all read from files the line already writes."
  - "Every runner records token usage per station on the run record. Cost is computed from a price table in config, never hard-coded, and is reported as unknown when the table is absent."
  - "A run links to its merged PR through a commit trailer (KeelSpec-Run: <run id>) that orchestrate prints for a proposed run, so cost per merged PR needs no GitHub API."
  - "The metrics schema moves to keelspec-metrics/2, and /1 fields stay unchanged."
---
**Already exists.** `keelspec/metrics.py` and `keelspec runs` report runs, status mix,
first-pass rate, repair rate, mean repair rounds, refutations by lens (counts), triage
causes, risk-tier mix and median duration, as `keelspec-metrics/1`. Run records already
hold verdicts, triage, approvals and timings. Evidence records already hold findings by
code.

**Genuinely new.** (1) Rates rather than counts for the critics. (2) Drift needs a
*history* of evidence records, and today nothing keeps one: `keelspec evidence` writes a
single file. (3) Token usage is not captured anywhere yet: the runners set `max_tokens`
but do not record usage. (4) Linking a run to a merged PR.

**Built (unreleased).** All six criteria, in `keelspec/metrics.py` and
`tests/test_metrics.py`. The line never commits, so it prints the trailer rather than
writing it; a person, or the tooling that opens the PR, puts it on the commit. The
cross-provider critic's call is not yet metered: it bypasses the station runner.
