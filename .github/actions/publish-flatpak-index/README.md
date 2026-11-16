# publish-flatpak-index

Wraps [`update-flatpak-index`](../update-flatpak-index) with the clone,
commit, and push against `tuna-os/docs` — with a retry loop, because that
push routinely loses a race.

## The bug this fixes

Every app repo's `publish-flatpak.yml` clones `tuna-os/docs`, edits its own
entry in `static/flatpak/index/static`, and does a plain `git push origin
main`. All ~8 app repos write to that same branch. When two publishes land
within the same push window (common — several apps publish on tag pushes
and `workflow_dispatch` fires in bursts), the second push is rejected:

```
! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'https://github.com/tuna-os/docs.git'
```

The job then fails outright. The OCI image was already pushed to GHCR
successfully by that point (`Push OCI to GHCR` is a separate, earlier
step), so the release exists and installs fine if you already know its
tag — but `flatpak remote-ls`/`flatpak update` never see it, because the
served index was never updated. Nothing retries; nothing alerts. The
release just silently doesn't show up.

## Usage

Replace the whole clone → update-index.py → commit → push block with:

Cross-repository callers use reviewed complete commit SHAs and keep pins current
through Renovate; see the [adoption policy](../../../docs/WORKFLOWS.md#adopting-a-workflow).

```yaml
- uses: tuna-os/.github/.github/actions/publish-flatpak-index@fded0603d7e383990e8259141419fe6c1d641f41 # main
  with:
    oci-dir: oci/mandelbrot-oci-x86_64
    repo-name: tuna-os/mandelbrot
    tags: latest
    ssh-key: ${{ secrets.FLATPAK_INDEX_DEPLOY_KEY }}
```

For multi-arch publishes, call it once per architecture, same as before —
each call is its own independent clone/retry/push cycle. `index-file`
defaults to `static/flatpak/index/static`, `registry` to `ghcr.io`,
`docs-repo` to `tuna-os/docs`.

On a rejected push, the action re-clones `docs-repo` at its new tip and
regenerates *this app's* entry against it before retrying (up to
`max-attempts`, default 8, with jittered backoff). This is safe because
`update-index.py` only ever replaces the `(repo-name, architecture)` entry
it was given — it never rewrites another app's entry, so replaying it on a
newer base can't clobber a concurrent writer's change.

## Credentials

`ssh-key` is the private half of a write deploy key on `docs-repo`. For
`tuna-os/docs` that key is the org secret `FLATPAK_INDEX_DEPLOY_KEY`, visible
to the publishing repositories only. It can write to the index repository and
nothing else, and it does not expire with a person's account, which is how
the PAT in `FLATPAK_INDEX_TOKEN` failed every publish in November 2026
(`permissions.push=HTTP 401`). `tuna-os/docs` lets deploy keys bypass its
`Markdown Lint` required check (repository ruleset), so the index commit can
land on `main` directly. The host key of github.com is pinned in the action.

Scope of `FLATPAK_INDEX_DEPLOY_KEY`: one repository (`tuna-os/docs`), Git
contents read and write over SSH, and no GitHub API access. It cannot open or
merge pull requests, change settings, or read another repository.

`token` still works for a caller that has not moved over; it is read only
when `ssh-key` is empty.

## Commit provenance

All index commits use the `github-actions[bot]` identity, whichever repository
made them. So the action ends each message with trailers that name the run:

```text
Source-Repository: tuna-os/example
Source-Workflow: tuna-os/example/.github/workflows/release.yml@refs/tags/v1
Source-Run: https://github.com/tuna-os/example/actions/runs/42/attempts/1
```

`git log --format='%(trailers:key=Source-Run)'` on `docs-repo` lists them.

## Generated icon artifacts

`tuna-os/docs` generates remote icon metadata and PNG files from the index
with `scripts/prepare-flatpak-icons.mjs`. Its site build and its sanity
workflow only check these artifacts. An index commit without them fails the
build, and then the new index does not deploy. When the cloned repository
contains that script, the action runs it with `node` after
`update-index.py` and commits the changes under `static/flatpak` with the
index.

## Migration status

Tracks tuna-os/tunaos#1183 (script duplication) and tuna-os/tunaos#2104
(this race). Adopted so far: Tavern, mariner, mandelbrot,
dualcut, gtk-office-suite (letters/tables/decks). Installer repos
(tuna-installer-{cosmic,kde,niri,xfce}, bootc-installer) still carry their
own copy of the old clone/push block — same follow-up scope #1183 already
called out for `update-index.py` itself.
