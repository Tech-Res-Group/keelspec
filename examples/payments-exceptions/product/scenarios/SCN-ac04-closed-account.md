---
id: SCN-ac04-closed-account
title: A credit transfer is rejected because the creditor account is closed
agent: AGENT-payment-exceptions
input: "Case 88121: pacs.002 RJCT AC04 on E2E-77F"
fixtures:
  TOOL-case-management.get_case: {case_id: "88121", end_to_end_id: E2E-77F, status: RJCT, reason: AC04}
  TOOL-payments-ledger.get_payment: {end_to_end_id: E2E-77F, amount_minor: 125000, currency: EUR, remittance: "INV-2231"}
  TOOL-iso20022-parser.explain_status: {code: AC04, meaning: "Account number specified has been closed on the bank of account's books"}
expect:
  must_call: [TOOL-case-management.get_case, TOOL-iso20022-parser.explain_status]
  must_not_call: [TOOL-case-management.release_funds]
  final_answer_contains: ["AC04", "closed"]
  outcome: completed
tags: [happy-path]
---
