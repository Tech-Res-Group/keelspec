---
id: FEAT-hosted-dashboard
title: "Enterprise edition: self-hosted first, a hosted tier later"
status: idea
outcome: OUT-agent-changes-pass-risk-review
customer_impact: medium
data: internal
reversible: true
acceptance:
  - "Runs entirely inside the customer's network. No data reaches the vendor, and the CLI never phones home."
  - "Collects keelspec-evidence and keelspec-metrics JSON from every repository (through an opt-in `upload:` input on the GitHub Action, off by default) and re-verifies each evidence record's digests on arrival."
  - "Retains and searches evidence, run records and approvals across repositories, so an audit question is answered without opening each repo."
  - "Central policy: risk tiers and required approvers set once for the organisation, and a repository cannot loosen them."
  - "Approvals signed through SSO identities with role-based access, replacing the self-asserted name in a commit."
  - "Exports evidence in a form the customer's audit and GRC tooling can ingest."
  - "A hosted tier with the same features comes later, for teams that can use SaaS. Selling it to regulated buyers would need SOC 2 or equivalent first."
---
**Decided (2026-11-16).** For regulated industries (banks and payments first, then
insurance, healthcare and medical devices, government suppliers and audited public
companies), the paid product is a **self-hosted enterprise edition**. The open-source
core stays Apache-2.0 and complete for one repository; the paid edition adds what only
matters across many repositories and to an auditor. Start with paid support and
onboarding for the first two or three regulated customers, and build the edition from
what they ask for.

**Already exists.** Stable, versioned JSON: `keelspec-evidence/1` (content-addressed and
verifiable) and `keelspec-metrics/1`. The reusable GitHub Action as the collection point.

**Genuinely new.** All of it: the service, storage and retention, policy, SSO and RBAC,
export, packaging for self-hosting. It should wait for FEAT-factory-metrics.

**Licence note.** The core is Apache-2.0, not LGPL. The moat is the enterprise edition
and the support, not the licence.
