# FastPDLC

**Product-as-code as a validated graph — for any project.**

Your product intent — the glossary, the constraints, the business rules, the
features, the decisions — usually lives as hopeful markdown that quietly rots. FastPDLC
turns it into **code**: you declare your typed artifacts in one config file, and it
loads them, enforces the schema and the cross-references, compiles a JSON bundle your
app or docs can render, and **fails CI when the committed bundle drifts**.

It started as the product-as-code engine inside a payments platform and was extracted
so any team can use it.

```bash
pip install fastpdlc
```

## Quickstart

1. Describe your artifact types in `product.config.yaml`:

   ```yaml
   product_dir: product
   output: build/product.generated.json
   types:
     - name: terms                 # a glossary
       dir: terms
       id_prefix: "TERM-"          # ids must be TERM-<slug> and match the filename
       required: [id, term, definition]
       fields: [term, definition, see_also]
       references:
         - field: see_also         # every see_also must resolve to another term
           to: terms
     - name: rules                 # the durable invariants
       dir: rules
       id_prefix: "BR-"
       required: [id, title, statement]
       fields: [title, statement]
   ```

2. Author artifacts as markdown-with-frontmatter under `product/`:

   ```markdown
   ---
   id: TERM-payment
   term: Payment
   definition: An instruction to move money between two parties.
   see_also: [TERM-ledger]
   ---
   The canonical unit of work in the system.
   ```

3. Build the bundle and gate it in CI:

   ```bash
   fastpdlc build       # -> build/product.generated.json  (commit it)
   fastpdlc validate    # schema + graph + staleness; non-zero exit on errors
   ```

## While you author

The gate is deterministic, which means everything it knows is available before you
push. Four surfaces expose the same graph, and **none of them forms its own opinion**
— every verdict below is `validate`'s, unchanged. An editor that said green while CI
said `PAC-020` would be a second judge, and a project whose whole claim is a
deterministic gate cannot afford two.

```bash
fastpdlc validate --watch          # the gate, re-run on every save
fastpdlc lsp                       # language server (pip install 'fastpdlc[lsp]')
fastpdlc mcp                       # the graph as tools (pip install 'fastpdlc[mcp]')
```

### `--watch`

Re-validates whenever a `product/` file, the config, or the committed bundle
changes. No extra dependency; it polls. Deliberately **not** a gate — it never exits
non-zero, so a red tree you are mid-fix does not kill the terminal you are fixing it
in. CI runs plain `validate`.

### The language server

Diagnostics, completion, hover, go-to-definition, find-references and workspace
symbols over your `product/` tree, in any LSP client — VS Code, JetBrains, Neovim,
Zed. A VS Code client lives in [`editors/vscode/`](editors/vscode/); it launches this
and owns no logic of its own.

Completion is the load-bearing one: in a reference field it offers the ids of the
type that field must resolve to, and in an enum field its members — both read from
the same config the validator reads, so **an accepted completion cannot be a
`PAC-020` or a `PAC-030`**. Hover shows what an id means and how many artifacts point
at it; find-references answers "what breaks if I retire this rule?".

Diagnostics come from the file *on disk*, so they refresh on **save** rather than on
every keystroke. That is the trade for having one judge. Completion, hover and
navigation do read the unsaved buffer, because they answer "what is here?" rather
than "is this allowed?".

### The MCP server

The same graph, spoken to an agent rather than an editor — because in a repo run this
way the author of `product/features/refunds.md` is increasingly a model, and asked
for a `constraints` list it will happily invent `CON-refund-window`.

Six read-only tools: `product_schema`, `product_list`, `product_get`,
`product_allowed_values`, `product_references_to` and `product_validate`. Read-only
on purpose — an agent proposes with its own tools, and a server that could also write
would let the thing being judged edit the evidence.

```json
{ "mcpServers": { "fastpdlc": { "command": "fastpdlc", "args": ["mcp"] } } }
```

## The agent-built lifecycle

`fastpdlc orchestrate` runs a station line over one artifact: **Understand →
Disambiguate (human gate) → Design → Develop → Test → adversarial Verify**, with a
bounded repair loop.

```bash
fastpdlc orchestrate FEAT-refunds                  # needs ANTHROPIC_API_KEY
fastpdlc orchestrate FEAT-refunds --no-clean       # skip the simplification pass
fastpdlc orchestrate FEAT-refunds --dry-run        # offline; exercises the pipeline
pip install 'fastpdlc[agents]'                     # the reasoning stations
```

Four critics attack the result through independent lenses — **correctness,
coverage, security, reproduce** — each defaulting to *refuted* unless convinced. A
blocking verdict feeds back to a repair round; after `--max-repair` rounds the run
reports honestly rather than proposing.

### The human gate

Open questions stop the line *before* design — building the wrong thing correctly is
the expensive failure. A blocking human gate cannot live inside one autonomous run,
so it is two-phase: run 1 writes the questions to
`.fastpdlc/disambiguations/<id>.json` and stops, a person fills in each `answer`,
run 2 reads them and proceeds.

```json
{
  "status": "pending",
  "questions": [
    { "id": "q1", "dimension": "refund window start",
      "question": "From authorization, settlement or delivery?", "answer": "" }
  ]
}
```

`--resolve q1="from settlement"` does the same thing inline for one-offs.

### Writing code

`Develop` is the only station that needs tools, so it runs a bounded loop with three
of them — list, read, write — confined to the project root. Absolute paths, `..` and
symlink escapes are refused, not sanitised; there is no shell, no network, and no
delete.

```bash
fastpdlc orchestrate FEAT-refunds            # proposes a diff, writes nothing
fastpdlc orchestrate FEAT-refunds --write    # lets it edit your working tree
```

`--write` is opt-in on purpose. Run it on a clean branch.

### A critic that does not share the builder's blind spots

```bash
OPENROUTER_API_KEY=... fastpdlc orchestrate FEAT-refunds --cross-provider
```

Adds a fifth verdict from a non-Claude model, joining the same refute/repair logic.
Diversity is a correctness lever: a critic from the same family can share the
builder's failure modes. Without the key the lens is skipped and the run is
identical to native-only; if the call fails it abstains rather than blocking.

### What is structural

- **Nothing merges.** The orchestrator's terminal state is a report. `validate` is
  the judge and a human decides; every station past the gate is deterministic or
  human by construction, and a test asserts it.
- **Minor findings do not block.** A gate that fires on nitpicks trains people to
  bypass it, and a bypassed gate is worse than none.
- **An unreachable critic abstains.** One flaky provider must not become an outage.

Control flow is ordinary code; reasoning lives inside a station. Supply your own
`Runner` to change what any station does.

## Evidence

`fastpdlc evidence` emits a content-addressed record of what was checked, when, on
which commit, and with what result — for the audit conversation that starts *"prove
your documented rules matched your implementation"*:

```bash
fastpdlc evidence -o build/evidence.json      # make a record
fastpdlc evidence --verify build/evidence.json # check one against this tree
```

Every artifact, the config and the bundle carry a SHA-256, so the record is verified
by recomputing digests rather than by trusting whoever produced it. Historical
evidence needs no special support: check out the commit and run it again — bundles
are byte-stable, so the digests match. Exit code follows `validate`, so it gates CI
and records it in one step.

## What `validate` enforces

Every finding carries a stable `PAC-NNN` code (an API — CI and dashboards match on the
code, never the prose):

| code | meaning |
|---|---|
| `PAC-001` | an artifact is missing a required field |
| `PAC-010` | an id doesn't start with its type's `id_prefix` |
| `PAC-011` | an id doesn't match its filename |
| `PAC-012` | a duplicate id within a type |
| `PAC-020` | a reference field doesn't resolve to a known artifact |
| `PAC-030` | a field value isn't in the type's allowed set (`enums`) |
| `PAC-060` | the committed generated bundle is missing or stale |

## Config reference

Each entry under `types`:

- **`name`** — the collection name (and the key in the bundle).
- **`dir`** — the subdirectory under `product_dir`.
- **`id_prefix`** *(optional)* — required id prefix; with **`id_matches_filename`**
  (default `true`), the id must equal the filename stem.
- **`required`** — frontmatter fields that must be present and non-empty (`id` always is).
- **`fields`** — the fields captured into the bundle.
- **`enums`** — `field -> [allowed values]`.
- **`references`** — `[{ field, to }]`: values of `field` must be the id of a `to` artifact.

## Extending it — plugins

Real projects need more than schema: cross-file checks ("does this `links.code` path
exist?"), derived bundle fields (reverse edges, rollups), extra generated outputs (a
runtime catalogue), and their own diagnostic codes. A **plugin** registers those without
forking the engine — which is how a large project migrates onto FastPDLC with **no loss
of functionality**:

```python
# product_hooks.py
from fastpdlc import register

def register(reg):
    register("PAC-900", "links.code path does not exist on disk")

    @reg.validator
    def code_paths_exist(bundle, config, root, report):
        for f in bundle["features"]:
            for path in f.get("code") or []:
                if not (root / path).exists():
                    report.add("PAC-900", f"missing {path}", f["_file"])

    @reg.bundle_transformer
    def reverse_edges(bundle, config, root):
        ...  # enrich the bundle in place

    reg.extra_output("build/catalogue.json", render_catalogue)  # staleness-gated too
```

```bash
fastpdlc -p product_hooks.py validate
```

## Start a new repo in one command

Scaffold a ready-to-go product-as-code repo (config, example artifacts, and the CI
gate) with the [copier](https://copier.readthedocs.io) template:

```bash
pipx run copier copy --trust gh:tarvitave/fastpdlc my-product-repo
```

`--trust` lets the template run `fastpdlc build` once so the new repo is valid on its
first commit.

## CI

Use the reusable Action — it installs FastPDLC and runs the gate:

```yaml
# .github/workflows/product.yml
name: product-as-code
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: tarvitave/fastpdlc@v0.4.0
        with:
          config: product.config.yaml     # optional (default)
          plugin: product_hooks.py         # optional project checks
```

<details><summary>Prefer plain pip?</summary>

```yaml
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install fastpdlc
      - run: fastpdlc validate
```
</details>

## Used in production

FastPDLC is the product-as-code engine of the **pharthing / KibiPay** payments
platform (50 features, a concept catalogue, 70 decisions, and a ~490 KB render bundle). pharthing's
CI runs `fastpdlc validate` as its sole gate via a plugin that adds domain checks — a
byte-identical parity test proves nothing was lost in the extraction. That's the
plugin system above, doing real work.

## Releasing

Publishing to PyPI is automated via GitHub Releases + Trusted Publishing — see
[RELEASING.md](RELEASING.md). Changes per version are in
[CHANGELOG.md](CHANGELOG.md).

## License

LGPL-3.0-or-later (copyleft, but you can import it as a library without your project inheriting the licence). See [LICENSE](LICENSE).
