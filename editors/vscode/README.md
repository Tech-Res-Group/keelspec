# KeelSpec for VS Code

Diagnostics, completion and navigation for a [KeelSpec](https://github.com/tarvitave/keelspec)
`product/` tree — the glossary, the constraints, the rules, the features and the
decisions that CI already gates.

## What it does

- **Diagnostics** — every `PAC-NNN` the gate reports, underlined on the line that
  caused it. `constraints: [CON-residency-pen]` is red as soon as you save, not when
  the pipeline goes red.
- **Completion** — field names for the artifact type you are in, and for a field's
  value: the ids of the type it must resolve to, or the members of its enum. Every
  offer comes from the same config the validator reads, so an accepted completion
  cannot be a `PAC-020` or a `PAC-030`.
- **Hover** — what an id means, and how many artifacts point at it.
- **Go to definition / Find all references** — jump to a rule; see everything that
  would break if you retired it.
- **Workspace symbols** — `Ctrl+T` over every artifact id in the tree.

## Requirements

The extension is a client. The server is the Python package:

```bash
pip install 'keelspec[lsp]'
```

It activates in any workspace containing a `product.config.yaml`.

## Settings

| Setting | Default | What it is |
|---|---|---|
| `keelspec.enable` | `true` | Run the server in this workspace. |
| `keelspec.path` | `keelspec` | The executable. Set an absolute path to pin a virtualenv. |
| `keelspec.config` | `product.config.yaml` | Config path, relative to the workspace root. |
| `keelspec.plugin` | `""` | Project plugin module or file (the `-p` flag). |

Using a virtualenv? Point `keelspec.path` at it — `.venv/bin/keelspec`, or
`.venv/Scripts/keelspec.exe` on Windows.

## One judge

Diagnostics come from `keelspec validate` itself, run over the files **on disk** —
the same bytes CI will read. Nothing is re-implemented in TypeScript, so the editor
cannot tell you something is fine when the gate disagrees. The consequence worth
knowing: underlines refresh on **save**, not on every keystroke. That is the trade,
and it is deliberate — a project whose whole claim is a deterministic gate cannot
afford a second opinion about what passes.

Completion, hover and navigation do read your unsaved buffer, because they answer
"what is here?" rather than "is this allowed?".

## Building it

Not published to the marketplace yet.

```bash
cd editors/vscode
npm install
npm run compile
```

Then `F5` in VS Code to launch an Extension Development Host, or package it with
`npx vsce package` and install the `.vsix`.
