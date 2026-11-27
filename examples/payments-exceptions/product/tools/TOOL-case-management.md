---
id: TOOL-case-management
title: Exceptions case management
transport: stdio
server: {command: python, args: ["-m", "servers.case_management"]}
operations:
  - name: get_case
    side_effects: read
    description: An exception case by id, with the status message that opened it.
    input_schema:
      type: object
      properties: {case_id: {type: string}}
      required: [case_id]
    fields: {customer.name: pii, customer.email: pii}
  - name: add_comment
    side_effects: write
    description: Add a finding to the case for the person who reviews it.
    input_schema:
      type: object
      properties: {case_id: {type: string}, text: {type: string}}
      required: [case_id, text]
  - name: propose_repair
    side_effects: money
    description: Propose a corrected payment for approval. Amounts are integer minor units.
    input_schema:
      type: object
      properties:
        case_id: {type: string}
        field: {type: string}
        new_value: {type: string}
        amount_minor: {type: integer}
      required: [case_id, field, new_value, amount_minor]
  - name: release_funds
    side_effects: money
    description: Release held funds for a case.
    input_schema:
      type: object
      properties: {case_id: {type: string}, amount_minor: {type: integer}}
      required: [case_id, amount_minor]
data_classes: [pii, financial]
timeout_seconds: 10
max_result_bytes: 65536
owner: payments-ops
status: building
---
The exceptions queue. `propose_repair` changes a value-bearing instruction and
`release_funds` moves money; the policies decide who may do either.
