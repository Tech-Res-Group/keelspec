# Releasing KeelSpec

Publishing is automated: `.github/workflows/publish.yml` builds and uploads to PyPI
when a GitHub Release is published. Auth is **PyPI Trusted Publishing (OIDC)** — no
API token is stored in the repo or in Actions secrets.

## One-time PyPI setup

Do this once, before the first release. It's the only manual step.

1. Log in at <https://pypi.org>.
2. Reserve the project name by creating a **pending publisher** (no upload needed
   first): go to <https://pypi.org/manage/account/publishing/> → *Add a pending
   publisher* and fill in:
   - **PyPI project name:** `keelspec`
   - **Owner:** `tarvitave`
   - **Repository name:** `keelspec`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. (Recommended) In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments) so the publish job's `environment: pypi` resolves and
   you can add release protection rules later.

That's it — no `PYPI_API_TOKEN`, no `twine` credentials.

## Cutting a release

1. Bump `version` in `pyproject.toml` (and note changes).
2. Commit, tag, and push:
   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push --follow-tags
   ```
3. Publish a **GitHub Release** from that tag (`gh release create vX.Y.Z --generate-notes`).
   That fires `publish.yml`, which asserts the tag matches `pyproject.toml`'s version,
   builds the sdist + wheel, and uploads to PyPI via OIDC.
4. Verify — but see the propagation note below before concluding anything failed.

Also update `CHANGELOG.md` in step 1, while the reasons for the changes are still to
hand.

### Verifying, and why it looks broken for a few minutes

**PyPI's JSON API updates before the index `pip` reads.** Immediately after a
successful publish, `https://pypi.org/pypi/keelspec/json` will list the new version
while `pip install` still reports *"from versions: <old>"*. That is CDN propagation,
not a failed release. It took about five minutes for 0.2.0.

Wait for the index rather than guessing:

```bash
until pip index versions keelspec 2>/dev/null | grep -q 'X\.Y\.Z'; do sleep 10; done
pip install "keelspec==X.Y.Z"
```

Two things that make a verification look like a failure when it is not:

- **Run it outside the repository.** Python puts the working directory on `sys.path`,
  so `import keelspec` from the repo root imports the local source tree, not what you
  just installed — and it will fail on a missing dependency the venv does not have.
- **Use a clean virtualenv**, so you are testing the published artifact rather than
  your editable install.

A genuinely failed publish shows up as a red run in
`gh run list --workflow=publish.yml`, not as a slow index.

**Fallback if the release event doesn't fire the workflow** (GitHub occasionally
doesn't trigger on `release`, e.g. after a delete/recreate): run it manually from
`main`, which must already carry the target version in `pyproject.toml`:

```bash
gh workflow run publish.yml -f version=X.Y.Z
gh run watch "$(gh run list --workflow=publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

## Versioning

KeelSpec follows semver. Diagnostic **codes are API** — never renumber an existing
`PAC-NNN` (retire and add). Changing the JSON bundle shape, a config key, or the
plugin `Registry` surface is a breaking change → bump the major.
