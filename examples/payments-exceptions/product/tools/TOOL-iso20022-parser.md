---
id: TOOL-iso20022-parser
title: ISO 20022 message parser
transport: stdio
server: {command: python, args: ["-m", "servers.iso20022_parser"]}
operations:
  - {name: parse_message, side_effects: none}
  - {name: explain_status, side_effects: none}
data_classes: [financial]
timeout_seconds: 5
max_result_bytes: 32768
owner: payments-platform
status: building
---
Parses pacs.008 and pacs.002 messages and explains a status reason code (AC04, AM05,
and the rest of the external code list) in plain words. Pure: no side effects.
