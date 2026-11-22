---
id: NFR-external-builder-contained
title: An external builder cannot edit what it is judged against
category: security
threshold: An external agent's work reaches the line only as the git diff of an isolated worktree. A diff that touches product_dir, the committed bundle, .keelspec/, or CI configuration fails the Develop step.
---
Today's Develop sandbox (keelspec/coding.py) guarantees list/read/write only, inside the
project root, with no shell, network or delete. Claude Code, Codex, Devin and Copilot's
agent all have a shell, and most have network access. The guarantee therefore has to
move from "what tools the agent has" to "what diff we accept", or the pitch "KeelSpec
decides what merges" is false for the very agents it names.
