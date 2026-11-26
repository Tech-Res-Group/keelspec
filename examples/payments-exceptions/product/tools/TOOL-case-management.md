---
id: TOOL-case-management
title: Exceptions case management
transport: stdio
server: {command: python, args: ["-m", "servers.case_management"]}
operations:
  - name: get_case
    side_effects: read
    fields: {customer.name: pii, customer.email: pii}
  - {name: add_comment, side_effects: write}
  - {name: propose_repair, side_effects: money}
  - {name: release_funds, side_effects: money}
data_classes: [pii, financial]
timeout_seconds: 10
max_result_bytes: 65536
owner: payments-ops
status: building
---
The exceptions queue. `propose_repair` changes a value-bearing instruction and
`release_funds` moves money; the policies decide who may do either.
