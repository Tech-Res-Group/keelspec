---
id: POL-repair-needs-approval
title: Any repair to a payment needs a human
effect: require_approval
match: {tool: TOOL-case-management, operation: propose_repair}
when: {arg: amount_minor, op: ">", value: 0}
approvers: [payments-ops-lead]
references: [CON-money-is-integer-minor-units]
---
A proposed repair is a change to a value-bearing instruction. The run stops until a
payments ops lead approves it. A repair with no amount matches no allow policy, so it
is denied by default.
