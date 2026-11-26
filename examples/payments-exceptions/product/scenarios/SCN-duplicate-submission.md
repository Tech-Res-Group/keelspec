---
id: SCN-duplicate-submission
title: A payment is rejected as a duplicate of one already settled
agent: AGENT-payment-exceptions
input: "Case 88140: pacs.002 RJCT AM05 on E2E-91C"
fixtures:
  TOOL-case-management.get_case: {case_id: "88140", end_to_end_id: E2E-91C, status: RJCT, reason: AM05}
  TOOL-payments-ledger.list_postings: {end_to_end_id: E2E-91C, postings: [{settled: true, amount_minor: 4000}]}
  TOOL-iso20022-parser.explain_status: {code: AM05, meaning: "Duplication"}
expect:
  must_call: [TOOL-iso20022-parser.explain_status, TOOL-payments-ledger.list_postings]
  must_not_call: [TOOL-case-management.propose_repair, TOOL-case-management.release_funds]
  final_answer_contains: ["AM05", "duplicate"]
  outcome: completed
tags: [idempotency]
---
The original already settled, so the right answer is no repair at all (BR-idempotent).
