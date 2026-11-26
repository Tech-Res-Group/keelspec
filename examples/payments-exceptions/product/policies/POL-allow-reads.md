---
id: POL-allow-reads
title: Reading and parsing are allowed
effect: allow
match: {side_effects: [none, read]}
rationale: An investigation has to see the payment. Reads change nothing.
---
Covers every operation whose side effect is `none` or `read`, on any tool the agent
declares. Writes and money operations need a policy of their own.
