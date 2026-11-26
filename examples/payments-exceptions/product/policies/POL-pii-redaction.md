---
id: POL-pii-redaction
title: Personal data is masked in tool results
effect: redact
match: {data_classes: [pii]}
rationale: The model needs the payment's shape, not the debtor's name or account.
---
Masks fields tagged `pii` in any result from a tool that handles personal data. It
does not permit a call on its own; every operation still needs an explicit allow.
