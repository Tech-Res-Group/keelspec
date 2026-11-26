---
id: TOOL-payments-ledger
title: Payments ledger (read)
transport: stdio
server: {command: python, args: ["-m", "servers.payments_ledger"]}
operations:
  - name: get_payment
    side_effects: read
    fields: {debtor.name: pii, debtor.account: pii, creditor.name: pii, creditor.account: pii}
  - {name: list_postings, side_effects: read}
data_classes: [pii, financial]
timeout_seconds: 10
max_result_bytes: 65536
owner: payments-platform
status: building
---
Read-only access to payment instructions and ledger postings by end-to-end id.
