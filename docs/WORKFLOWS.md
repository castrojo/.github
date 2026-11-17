# Reusable workflows

Reference documentation for the reusable (`workflow_call`) workflows that live in
[`.github/workflows/`](../.github/workflows) and are adopted by other
tuna-os repositories.

This is the org's central defaults repo. Reusable workflows are **public APIs**.
Cross-repository workflow and action references must use complete immutable
commit SHAs, kept current through Renovate (#285/#288/#335; migration tracker
[#152](https://github.com/tuna-os/.github/issues/152)). A caller adopts a workflow
revision when its pin update lands; a rollback restores a reviewed earlier SHA.
Legacy callers still tracking `@main` receive merges immediately until migrated.
Check callers before changing an input, default, or behaviour.

See [`AGENTS.md`](../AGENTS.md) for the different propagation mechanisms.

## Contents

- [Quick reference](#quick-reference)
- [Adopting a workflow](#adopting-a-workflow)
- [Workflows](#workflows)
  - [reusable-ci-contract](#reusable-ci-contractyml)
  - [reusable-fork-safety](#reusable-fork-safetyyml)
  - [reusable-lint](#reusable-lintyml)
  - [ste-lint](#ste-lintyml)
  - [reusable-scorecard](#reusable-scorecardyml)
  - [reusable-first-contributor](#reusable-first-contributoryml)
  - [reusable-pr-nudges](#reusable-pr-nudgesyml)
  - [reusable-add-help-wanted](#reusable-add-help-wantedyml)
  - [reusable-release-verification](#reusable-release-verificationyml)
  - [publish-flatpak](#publish-flatpakyml)
- [Common patterns and anti-patterns](#common-patterns-and-anti-patterns)
- [Testing changes before merge](#testing-changes-before-merge)
- [Troubleshooting](#troubleshooting)

## Quick reference

The workflows pinned in #163 use Ubuntu 24.04 LTS (`ubuntu-24.04`). Runner
version upgrades should be explicit changes reviewed through pull requests.
Other workflows already use versioned labels managed by Renovate.

| Workflow | File | What it does | Required inputs |
|---|---|---|---|
| CI Contract Verification | [`reusable-ci-contract.yml`](../.github/workflows/reusable-ci-contract.yml) | Asserts every green-criteria gate is wired to a reachable workflow | none (all optional) |
| Fork Safety Checks | [`reusable-fork-safety.yml`](../.github/workflows/reusable-fork-safety.yml) | Verifies `pull_request` workflows survive fork execution | none (all optional) |
| Lint | [`reusable-lint.yml`](../.github/workflows/reusable-lint.yml) | Runs shellcheck / yamllint / json-validate / actionlint / justfmt | none (all optional) |
| Simplified Technical English | [`ste-lint.yml`](../.github/workflows/ste-lint.yml) | Checks prose against ASD-STE100 against a per-repo budget | none (all optional) |
| Scorecard supply-chain security | [`reusable-scorecard.yml`](../.github/workflows/reusable-scorecard.yml) | Runs OpenSSF Scorecard | none (all optional) |
| First Contributor Greetings | [`reusable-first-contributor.yml`](../.github/workflows/reusable-first-contributor.yml) | Greets first-time issue/PR authors | none (all optional) |
| PR Reminders | [`reusable-pr-nudges.yml`](../.github/workflows/reusable-pr-nudges.yml) | Advisory reminders from the files a PR touches | none (all optional) |
| Add Help Wanted Label | [`reusable-add-help-wanted.yml`](../.github/workflows/reusable-add-help-wanted.yml) | Labels unassigned issues with `help wanted` | none |
| Release Verification | [`reusable-release-verification.yml`](../.github/workflows/reusable-release-verification.yml) | Fails unless a published release's tag, assets and checksums match a declared contract | `release-tag`, `expected-commit`, `expected-artifacts` |
| Publish Flatpak | [`publish-flatpak.yml`](../.github/workflows/publish-flatpak.yml) | Build → GHCR → central index pipeline | `app-id`, `manifest-path`, `repo-name` (+ `FLATPAK_INDEX_DEPLOY_KEY` secret) |

Inputs are grouped by responsibility below. `type` is the workflow-call input
type; `required: true` inputs must be supplied by every caller.

## Adopting a workflow

Every reusable workflow is called as a **job**, not a step. The caller keeps its
own `on:` trigger (the publish cadence and event type differ per repo) and
becomes a thin job that `uses:` the workflow at a reviewed full commit SHA:

```yaml
jobs:
  ci:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

The examples use the reviewed `main` revision `fded0603d7e383990e8259141419fe6c1d641f41`.
Keep pins current through Renovate; the `# main` comment records the tracked
branch, not a mutable execution ref. Do not copy an old pin without reviewing
the revision and available security updates.

The existing pin-checker `--self-repo` exemption covers only references into
the repository being checked. It is not a blanket exemption for first-party
org code. This documentation change does not alter that exception.

`publish-flatpak.yml` references its own composite actions (`arch-plan`,
`publish-flatpak-index`) as `$/.github/actions/...`, which GitHub resolves to
this repository at the commit the caller pinned, so those actions always match
the pinned workflow. The other reusable workflows still reference their
actions as `tuna-os/.github/.github/actions/<name>@main`. Callers' lockfiles
don't cover a called workflow's actions; this repository's
`.github/workflows/actions.lock` does, so those `@main` references run the
commit locked for `tuna-os/.github@main` there. After merging a change to one
of those actions, run `gh actions-lock --relock` here and merge that too, or
callers keep running the previously locked action. (They stay on `@main`
because `gh actions-lock` rewrites the SHA pins inside a `$/` composite action
to tags, and zizmor's `unpinned-uses` rejects tags in `action.yml` files:
lockfiles don't lock composite action definitions yet, gh-actions-lock#183.)

Two things are shared and two are per-caller:

- **Shared (defined by the reusable workflow):** the `runs-on` runner, the
  pinned action versions, the tool installation, and the job body.
- **Per-caller:** the `on:` trigger block, the `permissions:` block, and
  `secrets:` mapping (see the per-workflow sections for what each needs).

Do not leave production callers on feature-branch refs that can change or be
deleted. Test a candidate commit (see [Testing changes before merge](#testing-changes-before-merge)),
then update the caller to the reviewed merged commit SHA.

## Workflows

### reusable-ci-contract.yml

**Purpose.** Verifies that every green criterion in
.github/green-criteria.yml is actually
asserted by a *reachable* workflow (reachable = tied to an active trigger
through a `uses:` chain) and satisfies its freshness SLA. It is the check that
turns a list of desired CI properties into something CI proves.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `criteria-path` | string | no | `.github/green-criteria.yml` | Only if the criteria file lives elsewhere. |
| `workflows-dir` | string | no | `.github/workflows` | Only if workflows are not under the standard path. |
| `python-version` | string | no | `"3.11"` | Only to match a pinned Python; the check uses PyYAML only. |

**Usage.**

```yaml
jobs:
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** Exits `0` and skips if the criteria file is absent; exits `1` if the
workflows directory is missing. A criterion with a `gates` block but no
`freshness_sla_days`, or a gate that names a job/step which does not exist, is a
violation.

### reusable-fork-safety.yml

**Purpose.** Static verification that `pull_request` workflows survive execution
from a fork, where GitHub issues a read-only `GITHUB_TOKEN` and all repository
secrets are empty. It checks that (1) `pull_request` workflows declare explicit
`permissions`, (2) `pull_request_target` is not used without an explicit
exception, and (3) steps that write or reference secrets are guarded against the
fork case.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `workflows-dir` | string | no | `.github/workflows` | Only if workflows are not under the standard path. |
| `python-version` | string | no | `"3.11"` | Only to match a pinned Python; the check uses PyYAML only. |

**Usage.**

```yaml
jobs:
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** A step is considered guarded if the job `if`, the step `if`, its
`env`, or its `run` contains a fork guard such as
`github.event_name != 'pull_request'`, `head.repo.fork`, or
`steps.<id>.outputs` from a preflight job. `continue-on-error` on a step also
disarms the check for that step, so a write in a `continue-on-error` step is not
flagged — set `continue-on-error` deliberately.

### reusable-lint.yml

**Purpose.** Runs the org's static-analysis suite on shell scripts, YAML, JSON,
Justfiles, and workflows. Each check runs as its own matrix job so one failing
check does not cancel the others.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `checks` | string | no | `'["shellcheck", "yamllint", "json-validate", "actionlint", "justfmt"]'` | JSON array of checks. Each entry must be one of `shellcheck`, `yamllint`, `json-validate`, `actionlint`, `justfmt`. |

**Usage.**

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main

# Run only a subset, e.g. shellcheck and actionlint:
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
    with:
      checks: '["shellcheck", "actionlint"]'
```

**Notes.** `checks` is parsed with `fromJSON`, so it must be a valid JSON array
of strings — a bare string like `shellcheck` (not `["shellcheck"]`) fails to
parse and fails the job. `actionlint` checks both `.yml` and `.yaml` workflow
files, preserves diagnostics, and fails the job on lint errors. It skips when
neither extension is present. `justfmt` only runs when a top-level `Justfile`
exists.

### ste-lint.yml

**Purpose.** Checks Markdown and prose files against
[ASD-STE100](https://asd-ste100.org/) (Simplified Technical English) with a
per-repo budget. The linter and its rules live in the
[`.github/actions/ste-lint`](../.github/actions/ste-lint) composite action and
travel with it, so no repository carries a copy that can drift. Callers keep
their own `on:` trigger and become a thin job.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `budget-file` | string | no | `.ste-budget` | File holding the repo's maximum tolerated findings. |
| `budget` | string | no | `""` | Fallback budget when `budget-file` does not exist. Empty means "read the file only". |
| `node-version` | string | no | `"24"` | Node version the linter runs on. |
| `run-tests` | boolean | no | `true` | Run the linter's own test suite. Set `false` to skip. |
| `runs-on` | string | no | `ubuntu-24.04` | Runner label for the job. |
| `checkout-ref` | string | no | `""` | Ref to check out. Empty means the ref that triggered the caller. |

**Usage.**

```yaml
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

See [`.github/actions/ste-lint/README.md`](../.github/actions/ste-lint/README.md)
for what the check enforces, how to seed a budget, and how to opt a file out.

**Notes.** The checkout uses `fetch-depth: 0` because the advisory per-PR report
diffs the branch against its base (`github.base_ref`); a shallow checkout has no
base and the report degrades to whole-repo noise. On `pull_request` events the
advisory section reports only what the branch introduced and never decides
pass/fail — the budget gate does. An empty `github.base_ref` (non-PR events)
disables the advisory report and leaves the budget gate intact.

### reusable-scorecard.yml

**Purpose.** Runs [OpenSSF Scorecard](https://github.com/ossf/scorecard-action)
supply-chain security analysis and uploads the result to code scanning.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `publish-results` | boolean | no | `false` | Publish results to the OpenSSF REST API. Requires `id-token: write` (OIDC), which this workflow grants. |

**Usage.**

```yaml
jobs:
  scorecard:
    uses: tuna-os/.github/.github/workflows/reusable-scorecard.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** The job grants `security-events: write`, `id-token: write`,
`contents: read`, `actions: read`. To actually publish results set
`publish-results: true` and provide a token with the OpenSSF scope; leaving it at
the `false` default only uploads the SARIF to code scanning.

### reusable-first-contributor.yml

**Purpose.** Greets first-time contributors on issues and pull requests with a
welcome comment, once per author per repo. Bots (anything ending in `[bot]`,
`dependabot`, `github-actions`) are skipped.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `pr_message` | string | no | Welcome block for first PRs | Rewrite the welcome text. It is passed through `env:` to `github-script`, not interpolated into code. |
| `issue_message` | string | no | Welcome block for first issues | Rewrite the welcome text. |

**Usage.**

```yaml
jobs:
  greet:
    uses: tuna-os/.github/.github/workflows/reusable-first-contributor.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** The job needs `issues: write` and `pull-requests: write`; the caller
must grant them (or use `secrets`/`permissions` so the job can post comments).
It determines first-timers by searching for prior issues/PRs by the same author;
a count > 1 means the author has contributed before and the greeting is skipped.

### reusable-pr-nudges.yml

**Purpose.** Delivers advisory reminders to a pull request derived from the files
it touches. It runs the caller repository's nudge script (default
`.github/scripts/pr-nudges.sh`) and never fails a PR — reminders go to the step
summary and as annotations, plus a PR comment when permissions allow.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `script-path` | string | no | `.github/scripts/pr-nudges.sh` | Path to the caller's nudge script. |

**Secrets.**

| Secret | Required | Default | When to change it |
|---|---|---|---|
| `token` | no | `GITHUB_TOKEN` | Supply a token with comment scope if `GITHUB_TOKEN` cannot post PR comments in your repo's policy. |

**Usage.**

```yaml
jobs:
  nudges:
    uses: tuna-os/.github/.github/workflows/reusable-pr-nudges.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** The job is disabled for drafts, `renovate[bot]`, and `dependabot[bot]`
via its `if:`. It checks out only `script-path` (sparse checkout) and reads the
PR file list with `gh api --paginate` so a large PR cannot hide a path on page
two — this works on forks because reading needs no write permission. If the
script is missing it exits `0` and skips.

### reusable-add-help-wanted.yml

**Purpose.** Automatically adds the `help wanted` label to unassigned issues
once they are labelled `help wanted` or `good first issue`.

**Inputs.** None.

**Usage.**

```yaml
jobs:
  help-wanted:
    uses: tuna-os/.github/.github/workflows/reusable-add-help-wanted.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
```

**Notes.** The job needs `issues: write`. It runs with `continue-on-error` so a
transient API failure never blocks; it is a no-op if the issue already has a
label or an assignee.

### reusable-release-verification.yml

**Purpose.** Checks a release after it is published and fails closed if the
release does not match what the caller declared. It checks that the tag
resolves to the expected commit, that the release exists and is not a draft,
that every declared asset is present, and that each payload's SHA-256 matches
the entry in its checksum file. The [project-starter release
profile](../project-starter/README.md#release-verification-profile) wires it
into a new repository's `release.yml`.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `release-tag` | string | yes | — | The exact tag the publishing job created. |
| `expected-commit` | string | yes | — | The full 40-character SHA the tag must resolve to, normally the publishing job's `github.sha`. Abbreviated SHAs fail. |
| `expected-artifacts` | string | yes | — | JSON array describing each payload (see below). |
| `repository` | string | no | the caller's repository | Only to verify a release in another repository, as `owner/name`. |

`expected-artifacts` holds one object per payload. Each object has five
fields, and each field names a release asset: `name` (the payload),
`checksum`, `signature`, `provenance` and `sbom`. All five are required and
must not be empty, and no asset name may appear twice in the whole array.
The checksum file must have a `<sha256>  <name>` line for the payload (a
`./<name>` path also matches).

**Usage.** Run it as a job after the job that publishes the release:

```yaml
jobs:
  verify-release:
    needs: release
    permissions:
      contents: read
    uses: tuna-os/.github/.github/workflows/reusable-release-verification.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
    with:
      release-tag: ${{ needs.release.outputs.release-tag }}
      expected-commit: ${{ needs.release.outputs.expected-commit }}
      expected-artifacts: ${{ needs.release.outputs.expected-artifacts }}
```

`project-starter/.github/workflows/release.yml` shows how a publishing job
produces those outputs from `.github/release-artifacts.json`.

**Notes.**

- The signature, provenance and SBOM assets must exist and be non-empty, but
  the workflow does not verify the signature or read the provenance or SBOM.
  Add that verification separately if your release needs it.
- It calls the GitHub API with the caller's `GITHUB_TOKEN` and needs only
  `contents: read`. With `repository` set to another repository, that token
  must be able to read that repository's releases.
- The job writes a pass or fail summary, with links to each verified asset,
  to the run's step summary.
- `scripts/test-release-verification.py` runs the workflow's script against
  the fixtures in `tests/fixtures/release-verification/`.

### publish-flatpak.yml

**Purpose.** Canonical build → GHCR → central index pipeline for tuna-os flatpak
apps (tuna-os/tunaOS#1183). Callers keep their own `on:` trigger (publish cadence
differs per repo — tags-only, main+tags, PR-gated builds) and become a thin job
that `uses:` this with `secrets: inherit`.

**Inputs.**

| Input | Type | Required | Default | When to change it |
|---|---|---|---|---|
| `app-id` | string | **yes** | — | Flatpak application ID, e.g. `org.tunaos.mariner`. |
| `manifest-path` | string | **yes** | — | Path to the flatpak-builder manifest. |
| `repo-name` | string | **yes** | — | `owner/repo` on the registry and in the central index, e.g. `tuna-os/mariner`. |
| `archs` | string | no | `'["x86_64","aarch64"]'` | JSON array of architectures, limited to `x86_64` and `aarch64`. A preflight job fails the run before any build if the list is empty, has a duplicate, or names another value. Each arch is a separate build job and a separate index update. Unsuffixed `:latest` tracks `x86_64` when it is in the list, otherwise the first arch. |
| `flatpak-builder-image` | string | no | `gnome-50` | `flathub-infra/flatpak-github-actions` image tag (without the `ghcr.io/flathub-infra/flatpak-github-actions:` prefix). |
| `checkout-submodules` | boolean | no | `false` | Checkout submodules of the source. |
| `source-repo` | string | no | `''` | `owner/repo` to build from when the source is **not** the calling repo (e.g. republishing Ghostty from `tuna-os/blueshell`). Empty checks out the caller at the calling ref. |
| `source-ref` | string | no | `''` | Branch/tag/SHA within `source-repo`. Empty means that repo's default branch. Ignored when `source-repo` is empty. |
| `attach-bundles` | boolean | no | `false` | Build a `.flatpak` bundle per arch and attach it to the GitHub release on tag push. |
| `generate-cargo-sources` | boolean | no | `false` | Run `flatpak-cargo-generator` against `cargo-lock-path` before building. The generator is pinned to a reviewed upstream commit and SHA-256-verified before it runs; bump both values in the step together. |
| `cargo-lock-path` | string | no | `Cargo.lock` | Cargo lock file path for the generator. |
| `cargo-sources-output` | string | no | `build-aux/cargo-sources.json` | Output path for the generated cargo sources. |
| `publish` | boolean | no | `true` | Push to GHCR and update the index. Set `false` for build-only validation (e.g. on `pull_request`). |
| `registry` | string | no | `ghcr.io` | Registry host. |

**Secrets.**

| Secret | Required | Default | When to change it |
|---|---|---|---|
| `FLATPAK_INDEX_DEPLOY_KEY` | one of the two | — | Private half of the write deploy key on `tuna-os/docs` (the central index); org secret, visible to the publishing repos. Preferred. Map it with `secrets: inherit` or explicitly. |
| `FLATPAK_INDEX_TOKEN` | one of the two | — | Legacy token allowed to push `tuna-os/docs`. Read only when `FLATPAK_INDEX_DEPLOY_KEY` is empty. |

**Usage.**

```yaml
jobs:
  publish:
    uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@fded0603d7e383990e8259141419fe6c1d641f41 # main
    with:
      app-id: org.tunaos.mariner
      manifest-path: org.tunaos.mariner.json
      repo-name: tuna-os/mariner
    secrets: inherit
```

**Notes.**

- The job takes `contents: write` (checkout + `gh release upload`) and
  `packages: write` (GHCR push + index push). The caller must grant them or let
  `secrets: inherit` + the workflow's own `permissions:` handle it.
- `source-repo` lets a caller publish an app whose source lives elsewhere. The
  upstream repo is checked out untouched and built with its own manifest, so
  upstream dependency/runtime bumps need no action here. The app still lands on
  the registry and index under `repo-name`.
- `publish` is a matrix with one job per planned arch. Each job downloads its
  own OCI artifact, pushes its own arch tags, and calls `publish-flatpak-index`
  with its own clone/retry/push cycle against `tuna-os/docs`.
- Before the build, each `build-oci` job runs the `flatpak-copy-up` action.
  On some hosts, the job cannot update the runtimes in the image. On these hosts,
  the update fails with `Invalid cross-device link`. The action prevents this
  failure. The image digest does not change between hosts, so a digest pin
  does not help.
- `attach-bundles` only runs on tag pushes (`startsWith(github.ref, 'refs/tags/')`).
- Not used by `tuna-os/Tavern`: it has a prod/main branch split and a promotion
  flow this workflow does not model (tuna-os/tunaOS#1183).

## Common patterns and anti-patterns

For safe input and context handling in `run:`, including quoting and list
arguments, see [Safe environment variables in GitHub Actions](ACTION_SECURITY.md).

| Do | Avoid |
|---|---|
| Call a reusable workflow as a **job** (`jobs.x: uses:`). | Calling it as a **step** — `workflow_call` jobs cannot run inside another job's `steps:`. |
| Pin cross-repository workflows/actions to complete commit SHAs; keep pins current through Renovate. | Mutable branches/tags, including first-party `@main` outside the same-repository exception; stale pins with no update process. |
| Keep the `on:` trigger and `permissions:` on the caller. | Moving triggers into the reusable workflow — the org workflow has no trigger of its own by design. |
| Map secrets explicitly or use `secrets: inherit`. | Relying on implicit secret availability; fork runs have empty secrets. |
| Change a default only after checking callers (`git grep` the org for the workflow). | Renaming an input or changing what a default means — callers break silently at their next run. |
| For `reusable-lint`, pass a JSON **array** in `checks`. | Passing a bare string; `fromJSON` on a non-array fails the job. |
| Seed `ste-lint` with the current finding count, not `0`. | Setting a budget of `0` — a gate that fails on day one gets disabled on day two. |

## Testing changes before merge

Do not merge unverified: legacy `@main` callers receive changes immediately,
and SHA-pinned callers receive workflow revisions through pin updates. Existing
same-repository mutable nested references remain live under the documented
exception. Two complementary strategies:

**1. Test the underlying tooling locally.** Most reusable workflows are thin
wrappers; verify the thing they actually run before touching the `uses:` line.

- `ste-lint`: run the linter from a checkout of this repo —
  `node .github/actions/ste-lint/ste-lint.mjs --summary`, or `just ste`. For
  per-PR detail: `node .github/actions/ste-lint/ste-lint.mjs --changed-only
  --base origin/main --format json`.
- `reusable-lint`: run the same tools locally (shellcheck, yamllint, jq,
  actionlint, `just --fmt --check`). `actionlint .github/workflows/*.yml`
  catches workflow-syntax errors before they reach CI.
- `reusable-ci-contract` / `reusable-fork-safety`: they run an embedded Python
  heredoc (PyYAML). Reproduce by running the equivalent script against your
  local `.github/workflows` and criteria file.
- `publish-flatpak`: run with `publish: false` for a build-only validation that
  never touches GHCR or the index.

**2. Exercise the candidate workflow commit.** A normal PR check does not by
itself prove that a reusable workflow's edited body executed: an existing
caller still points at its configured ref. To exercise the candidate:

1. Push the candidate commit to your fork.
2. In a test caller, reference its full SHA (replace the placeholders):
   ```yaml
   jobs:
     test:
       uses: <your-fork>/.github/.github/workflows/reusable-lint.yml@<full-candidate-commit-sha>
   ```
3. Trigger the caller on a supported event and inspect the result. For manual
   testing, add `workflow_dispatch` to the caller, not the reusable workflow.
4. After review and merge, update production callers to the reviewed merged
   commit SHA, not the temporary fork ref.

For composite actions a reusable workflow depends on (e.g. `ste-lint` and
`publish-flatpak-index`), ensure the test actually references the candidate
action SHA too. `publish-flatpak.yml` uses `$/` references, so calling the
candidate workflow commit also runs that commit's actions. The other
workflows' `@main` references run the commit locked in this repository's
`actions.lock`, not necessarily the edited candidate.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `reusable-lint` job fails to start with a JSON parse error | `checks` is not a valid JSON array | Quote a JSON array: `checks: '["shellcheck"]'`, not `checks: shellcheck`. |
| `ste-lint` advisory report on a PR lists the whole repo, not just the diff | Shallow checkout (`fetch-depth < 0` missing) | The workflow fetches full history; if you forked the workflow, keep `fetch-depth: 0`. |
| `ste-lint` passes on `push` but the advisory is empty on a PR | `github.base_ref` is only set on `pull_request` | The advisory is intentionally disabled off-PR; the budget gate still runs. |
| Fork run fails on a step that works in the same-repo run | Forks get a read-only token and empty secrets | Guard the step with `github.event_name != 'pull_request'` or a preflight check; never rely on secrets in a `pull_request` path. |
| `reusable-fork-safety` flags a `pull_request_target` workflow | `pull_request_target` exposes secrets to untrusted code | Switch to `pull_request`, or add an explicit, documented exception in the workflow. |
| `publish-flatpak` index push is rejected (`fetch first`) | Concurrent publishes race on `tuna-os/docs` | Expected — the action retries with backoff. Frequent rejects mean publishing two apps in the same push window; the retry handles it. |
| `publish-flatpak` fails `missing oci-x86_64` | `download-artifact` with a single-match `pattern` flattens into the job root | The workflow downloads each arch by explicit name+path, not by pattern; do not change this to a glob. |
| `reusable-ci-contract` reports "not reachable" | A gate workflow is not tied to an active trigger through a `uses:` chain | Wire the gate into a workflow with a live trigger (`push`, `pull_request`, `schedule`, …). |
| `reusable-ci-contract` reports "missing freshness_sla_days" | A criterion has a `gates` block but no freshness SLA | Add `freshness_sla_days` to that criterion. |
| `reusable-first-contributor` never greets | Author already has a prior issue/PR, or is a bot | Expected for repeat contributors and `[bot]` / `dependabot` / `github-actions`. |

## Related

- [`AGENTS.md`](../AGENTS.md) — how changes to these paths land everywhere at once.
- [`.github/actions/ste-lint/README.md`](../.github/actions/ste-lint/README.md)
  — what `ste-lint` checks and how to seed its budget.
- [`.github/actions/publish-flatpak-index/README.md`](../.github/actions/publish-flatpak-index/README.md)
  — the central-index push behind `publish-flatpak.yml`.
