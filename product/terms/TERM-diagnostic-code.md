---
id: TERM-diagnostic-code
term: Diagnostic code
definition: >-
  The stable identifier on every finding the validator reports — `PAC-020` for an
  unresolved reference, `PAC-060` for a stale bundle. Engine codes occupy
  PAC-0xx through PAC-06x; consumer plugins register theirs from PAC-9xx.
aka: [PAC code]
see_also: [TERM-artifact]
---
The code is the part consumers depend on, which is why a released one never
changes meaning — [`CON-codes-are-an-api`](../constraints/CON-codes-are-an-api.md).
A finding also carries a severity, a message, a file and, where the engine can
locate it, the field and value it is about; only the code is a promise.
