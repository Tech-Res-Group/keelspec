# Decisions: governed agents

The open decisions from the governed-agents spec, as settled on 2026-11-27. Each one
records what was decided and why, so a later change is a deliberate reversal and not
drift.

| | Decision | Why |
|---|---|---|
| D-1 | **Version 1.0.0, a major.** 1.0.0 was tagged but never reached PyPI; 1.0.1 is the first installable release. | `presets` and list-valued `references[].to` are config-schema changes, which the versioning policy treats as major. |
| D-2 | **Map agents to existing FifeRouter concepts** (`moneypath.verify`, `general.assist`). Propose an `ops.investigate` concept only once run records show the need. | Run records already log the concept each run used, so the proposal can come with evidence instead of a guess. |
| D-3 | **Native YAML policies. No OPA/Rego.** Revisit only if a customer asks. | `policy explain` and the policy lens depend on deterministic native semantics. A second language would need its own lens. |
| D-4 | **Everything stays Apache-2.0, including `serve`.** | The pitch is a gate that a risk function can audit. Closed code in that path would undercut it. Revenue comes from support, evidence retention and services, not from the trust path. |
| D-5 | **No default model endpoint.** `router.base_url` must be set in `keelspec.runtime.yaml`; `run` and `serve` refuse to start without it. Hosted FifeRouter is offered as the easy option in the example and the error message. | The first audience is payments and financial services. Sending prompts and tool data to a shared service by default is the first thing their risk review would flag. |
| D-6 | **The product stays KeelSpec; the feature is "governed agents".** No "v2" label and no separate product name. | Keeps the naming brief: KeelSpec is the product, FastPDLC is the method. "KeelSpec v2" next to version 1.0 would confuse. |
| D-7 | **Cleared.** The owner confirmed that no outside-activity or invention-assignment terms apply. KeelSpec is released as open source by `tarvitave`, the copyright holder. | Checked by the owner before the first public 1.x release. |
