---
id: POL-no-funds-movement
title: The agent never releases funds
effect: deny
match: {tool: TOOL-case-management, operation: release_funds}
references: [CON-money-is-integer-minor-units]
rationale: Releasing funds is a person's decision, always.
---
No condition: this denial applies to every call, whatever the arguments, and no other
policy can outrank a deny.
