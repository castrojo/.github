# Shared CI & Actions Guide for tuna-os/.github

This guide is the onboarding entry point for any repository adopting the
shared tooling in [`tuna-os/.github`](https://github.com/tuna-os/.github). It
answers the four questions new repos keep asking:

1. **Which workflow or action do I need?** (selection criteria)
2. **How do they compose?** (integration patterns)
3. **What must I set up before I adopt one?** (prerequisites)
4. **What is failing and why?** (troubleshooting)

Each tool also has its own README with deeper detail; this document is the
map, not the territory. See [References](#references) for the links.

## What this repository is

`tuna-os/.github` is the org's **defaults repository**. It ships nothing that
builds a product; everything here applies to other repositories. Four
mechanisms push a change here out to the whole org at once — read
[`AGENTS.md`](https://github.com/tuna-os/.github/blob/main/AGENTS.md) for the
full account, but the short version is:

- `.github/workflows/*.yml` declared with `on: workflow_call` are **reusable
  workflows** that any repo calls with `uses: tuna-os/.github/...@main`.
- `.github/actions/*` are **composite actions** that any repo calls the same
  way.
- Callers pin to `@main`. A merge into `main` here reaches every caller on their next run. There is no version to hold a consumer back, and
  the only rollback is another commit. **Treat every `inputs:` block as a public API.** Rename an input or change a default and the run breaks
  callers silently.

Because of that, **do not copy a workflow or action into your repo.** Call it.
The actions deliberately travel with themselves so no repository carries a
copy that can drift.

## Current inventory

The issue that started this guide counted "7 reusable workflows". As of this
writing there are **9 reusable workflows and 3 composite actions**
(`publish-flatpak.yml` and `ste-lint.yml` are also reusable). This list is
authoritative — refresh it against the repo if it ever looks stale.

### Reusable workflows

| Workflow file | One-line purpose | Adopt when |
|---|---|---|
| `reusable-lint.yml` | Static checks: shellcheck, yamllint, json-validate, actionlint, justfmt | You want a baseline quality gate on every PR |
| `reusable-ci-contract.yml` | Verifies your `.github/green-criteria.yml` is actually asserted by reachable jobs | You maintain a self-defined CI contract and want to enforce it |
| `reusable-fork-safety.yml` | Checks every `pull_request` workflow is fork-safe (permissions, no `pull_request_target`, guarded writes) | You want a security gate against unsafe fork handling |
| `ste-lint.yml` | ASD-STE100 (Simplified Technical English) prose check against a per-repo budget | You want machine-readable, plain-English docs |
| `reusable-scorecard.yml` | OpenSSF Scorecard supply-chain analysis → SARIF → Code Scanning | You want a security posture score published to the repo |
| `reusable-first-contributor.yml` | Greets first-time contributors on issues and PRs | You want warmer onboarding |
| `reusable-add-help-wanted.yml` | Adds `help wanted` to unassigned issues carrying `help wanted`/`good first issue` | You want help-wanted issues to be easy to find |
| `reusable-pr-nudges.yml` | Advisory reminders derived from the files a PR touches (runs your own script) | You want contextual, non-blocking PR hints |
| `publish-flatpak.yml` | Canonical build → GHCR → central index pipeline for flatpak apps | You publish a Flatpak application |

Use reusable workflows as **jobs**, not steps. Each reusable workflow
keeps its own `on:` trigger block, so **your** workflow defines the triggers
and becomes a thin job that `uses:` the shared one:

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
```

### Composite actions

| Action dir | One-line purpose | Adopt when |
|---|---|---|
| `update-flatpak-index` | Reads a local OCI layout and updates one app's Flatpak index entry (digest, arch, labels, optional AppStream validation) | You need the low-level index update primitive |
| `publish-flatpak-index` | Wraps `update-flatpak-index` with clone → update → commit → push to `tuna-os/docs`, retrying against concurrent writers | You publish a flatpak and want the index updated safely |
| `ste-lint` | The STE linter and its rules (ships the `.mjs` linter, rules, and tests) | You need the STE check inside a custom job, or want to run it locally |

Most repos should use the **reusable `ste-lint.yml` workflow**, not the
`ste-lint` action directly. Reach for the action only when you need to embed
the linter in a custom job or run it off a checkout.

### Workflows that are NOT for adoption

Three workflows live in `.github/workflows/` but run **only inside
`tuna-os/.github` itself**. Do not call them from other repos:

- `renovate-policy-check.yml` — enforces the automerge policy against this
  repo's own `renovate.json`.
- `drop-bot-review-requests.yml` — drops auto-requested reviewers on
  bot-authored PRs so routine dependency bumps stop pinging humans.
- `flatpak-tooling-drift-check.yml` — weekly check that no repo has drifted
  from the canonical `update-index.py`.

## Decision tree

- "I want baseline lint (shell/YAML/JSON/actionlint/Justfile) on every PR"
  → **`reusable-lint.yml`**
- "I want to prove my green-criteria run in reachable jobs" →
  **`reusable-ci-contract.yml`** (needs `.github/green-criteria.yml`)
- "I want to make sure my PR workflows are safe from forks" →
  **`reusable-fork-safety.yml`**
- "I want my docs in plain, machine-checkable English" →
  **`ste-lint.yml`** (needs `.ste-budget`)
- "I want a supply-chain security score in Code Scanning" →
  **`reusable-scorecard.yml`** (enable Code Scanning)
- "I want to welcome first-time contributors" →
  **`reusable-first-contributor.yml`**
- "I want `help wanted` added to unassigned issues automatically" →
  **`reusable-add-help-wanted.yml`**
- "I want contextual, non-blocking hints about what a PR touches" →
  **`reusable-pr-nudges.yml`** (needs `.github/scripts/pr-nudges.sh`)
- "I publish a Flatpak app" → **`publish-flatpak.yml`** + the
  **`publish-flatpak-index`** / **`update-flatpak-index`** actions

## Common setups

Copy these as a starting point. Change the trigger list to match your publish
cadence. Each shared workflow is called as a job, so your `on:` block is the
only thing that is truly yours.

### Minimal PR checks

Lint and a fork-safety gate. Enough for most utility repos.

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main
```

### Enforce a CI contract + prose style

For repos that keep a green-criteria file and care about STE.

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
    with:
      budget-file: .ste-budget
```

### Full adoption

All nine shared workflows, plus the two greeting and reminder helpers. The
shared workflows carry their own `if:` guards, so it is safe to include them
all. Each helper skips cases on its own: `pr-nudges` skips drafts and bots,
`add-help-wanted` skips labeled issues, and `first-contributor` skips authors
who contributed before.

```yaml
name: CI
on:
  pull_request:
  issues:
    types: [labeled]
  push:
    branches: [main]

jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
    with:
      budget-file: .ste-budget
  scorecard:
    uses: tuna-os/.github/.github/workflows/reusable-scorecard.yml@main
  first-contributor:
    uses: tuna-os/.github/.github/workflows/reusable-first-contributor.yml@main
  help-wanted:
    uses: tuna-os/.github/.github/workflows/reusable-add-help-wanted.yml@main
  pr-nudges:
    uses: tuna-os/.github/.github/workflows/reusable-pr-nudges.yml@main
```

`issues: [labeled]` is required for the help-wanted and first-contributor
helpers, which read `context.payload.issue`.

### Publish a Flatpak app

Your app repo keeps its own trigger (tags-only, `main`+tags, PR-gated, …) and
becomes a thin job that `uses:` the shared publish workflow with
`secrets: inherit`:

```yaml
name: Publish
on:
  push:
    tags: ["v*"]

jobs:
  publish:
    uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@main
    with:
      app-id: org.tunaos.mandelbrot
      manifest-path: org.tunaos.mandelbrot.yml
      repo-name: tuna-os/mandelbrot
    secrets: inherit
```

That pipeline calls `publish-flatpak-index` internally to update the central
index in `tuna-os/docs`. You only touch the `update-flatpak-index` or
`publish-flatpak-index` actions directly if you are building a publish flow
outside the shared workflow.

## Prerequisites checklist

Do these before wiring up the workflows:

- **Sign every commit.** `git commit -s` (DCO). The merge tool blocks the merge without
  the sign-off trailer, and the trailer's email must match the commit author.
- **`reusable-lint.yml`** — optional but recommended: a `.yamllint.yml`/`.yamllint.yaml`
  (the linter picks it up automatically) and a `Justfile` (the `justfmt` step checks
  it only if present). Install the tools locally to reproduce:
  `brew install just shellcheck shfmt yamllint jq actionlint`.
- **`ste-lint.yml`** — create `.ste-budget`. Seed it with the repo's current
  finding count, not `0`. A gate that fails on day one gets disabled on day
  two:
  ```sh
  node .github/actions/ste-lint/ste-lint.mjs --summary
  ```
  Take the total, commit it as `.ste-budget`, then lower it over time. The
  check covers `README.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, and `docs/`/`blog/` if present.
- **`reusable-ci-contract.yml`** — create `.github/green-criteria.yml`
  describing the criteria you want enforced. The workflow skips cleanly if the
  file is absent.
- **`reusable-scorecard.yml`** — enable **Code Scanning** in the repo
  settings (Settings → Code scanning). The job needs
  `security-events: write`, `id-token: write`, and `actions: read`, which the
  shared workflow declares by default.
- **`reusable-pr-nudges.yml`** — add `.github/scripts/pr-nudges.sh`. The
  workflow skips gracefully (exit 0) if the script is missing.
- **`publish-flatpak.yml`** — add a `FLATPAK_INDEX_TOKEN` secret with push
  access to `tuna-os/docs` (Contents: write). The action fails fast if the
  token cannot push, instead of wasting retries on an auth problem.
- **`reusable-first-contributor.yml` / `reusable-add-help-wanted.yml`** — add
  the `issues` event to your `on:` block (see the full-adoption example).

## Troubleshooting

**"STE budget exceeded: 251 > 247"**
Run `node .github/actions/ste-lint/ste-lint.mjs --summary` to list findings
per file. Fix the flagged prose (use the linter's replacement where it gives
one), or opt the file out *in its own text* with a reason. Then lower
`.ste-budget`.

**"fork-safety: job 'x' lacks explicit `permissions:` declaration"**
Add a `permissions:` block to the flagged job (or at the top of the workflow).
`tuna-os` forbids `pull_request_target` outright — remove it, not carve an exception.

**"ci-contract: <workflow> is not reachable from any active trigger"**
A gate workflow must be reachable from `push`, `pull_request`, `schedule`,
`workflow_run`, `release`, or `merge_group` — either directly or through
another reusable workflow. Make sure the gating workflow fires.

**"publish-flatpak-index: rejected … (fetch first)"**
This is expected: up to ~8 app repos push to `tuna-os/docs` at once. The
action retries with jittered backoff (default `max-attempts: 8`). It only
fails after it tries that many times; if so, space out your publishes
or raise `max-attempts`. A non-race failure (auth, branch protection) fails
immediately with the real reason — do not treat that as a race.

**"scorecard produced no results / no SARIF uploaded"**
Code Scanning is not enabled, or the repo lacks the `id-token: write`
permission. Enable Code Scanning and confirm the job permissions.

**"Reference 'tuna-os/.github/...@main' not found" / 404 on `uses:`**
The org defaults to `main` (see the note below about default branches). Confirm
the branch name and that the workflow file exists at that ref.

**"The shared workflow changed and my CI broke"**
That is the propagation model working. A merge here reaches every caller. Read
the upstream PR, update your usage if an input changed, and pin back only if
you must hold a consumer back.

## FAQ

**Do I copy any of these files into my repo?**
No. Call them with `uses:`. The composite actions ship their own code so no
repo carries a copy to drift.

**Why pin to `@main` and not a release tag?**
The org pins to `main` so a merge is live for all callers at once. Accept the
tradeoff: you move with the repo. See `AGENTS.md`.

**Can I edit a shared workflow to fix my problem?**
Edit it upstream in `tuna-os/.github` via a PR. Changes propagate everywhere.
Never fork one into your repo to make a local change — it will drift.

**`pull_request_target` — can I use it?**
No. `tuna-os` forbids it because it exposes secrets and a write token to
untrusted fork code. `reusable-fork-safety.yml` fails any workflow that uses
it.

**Which branch do PRs to this repo target?**
`main` (some other tuna-os repos default to something else — resolve the
default branch per repo, never assume). See `AGENTS.md` and
[`ROADMAP-INDEX.md`](https://github.com/tuna-os/.github/blob/main/ROADMAP-INDEX.md).

## References

Reusable workflows (`.github/workflows/`):

- [`reusable-lint.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-lint.yml)
- [`reusable-ci-contract.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-ci-contract.yml)
- [`reusable-fork-safety.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-fork-safety.yml)
- [`ste-lint.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/ste-lint.yml)
- [`reusable-scorecard.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-scorecard.yml)
- [`reusable-first-contributor.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-first-contributor.yml)
- [`reusable-add-help-wanted.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-add-help-wanted.yml)
- [`reusable-pr-nudges.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/reusable-pr-nudges.yml)
- [`publish-flatpak.yml`](https://github.com/tuna-os/.github/blob/main/.github/workflows/publish-flatpak.yml)

Composite actions (`.github/actions/`):

- [`ste-lint`](https://github.com/tuna-os/.github/tree/main/.github/actions/ste-lint) — README
- [`update-flatpak-index`](https://github.com/tuna-os/.github/tree/main/.github/actions/update-flatpak-index) — README
- [`publish-flatpak-index`](https://github.com/tuna-os/.github/tree/main/.github/actions/publish-flatpak-index) — README

Other:

- [`AGENTS.md`](https://github.com/tuna-os/.github/blob/main/AGENTS.md) — blast radii, invariants, checks
- [`CONTRIBUTING.md`](https://github.com/tuna-os/.github/blob/main/CONTRIBUTING.md) — branch prefixes, DCO, PR checklist
- [`docs/OBSERVABILITY.md`](https://github.com/tuna-os/.github/blob/main/docs/OBSERVABILITY.md) — a sibling high-level guide
