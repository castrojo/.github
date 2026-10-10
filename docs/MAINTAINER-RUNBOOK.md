# Maintainer Runbook for tuna-os/.github

Operational procedures for the `tuna-os/.github` org-defaults repository. This
complements [`AGENTS.md`](../AGENTS.md) (architecture) and
[`CONTRIBUTING.md`](../CONTRIBUTING.md) (how to contribute) with the day-to-day
"what do I actually do when X breaks" knowledge.

## Read this first: what this repo is

Nothing here builds a product. Every artifact here is consumed by other
repositories, so a change here lands everywhere at once:

| Path | Reaches |
|---|---|
| `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `DISCUSSION_TEMPLATE/`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` | Every org repo that does not ship its own copy — immediately, no merge in that repo |
| `profile/README.md` | The organisation's public landing page |
| `.github/workflows/*.yml` with `on: workflow_call`, and `.github/actions/*` | Every repo that `uses:` them — callers pin `@main`, so a merge is live for them |
| `project-starter/` | A template **copied** into new repos; not used by this repo |

There is no version to hold a consumer back and no rollback except another
commit. `publish-flatpak.yml`'s inputs and each action's `inputs:` block are a
public API: renaming one, or changing what a default means, breaks callers
silently at their next run. **Treat every change as if it were published to
every repo at once.**

## Conventions (do not skip)

- **Target branch:** `main`. This is the org-default branch and the branch
  callers pin (`@main`). Open PRs against `main` unless an issue names another.
- **Sign every commit:** `git commit -s` (DCO). The merge is blocked without a
  `Signed-off-by` trailer, and the trailer's email must match the commit
  author's email.
- **Branch prefixes:** `arch/`, `fix/`, `feat/`, `chore/`, `docs/` — see
  `CONTRIBUTING.md`.
- **Verification gates** (run before opening a PR; both are enforced in CI):

  ```bash
  python3 scripts/check-renovate-automerge-policy.py renovate.json
  python3 scripts/check-workflow-permissions.py .github/workflows
  ```

  Both must pass. The first enforces the renovate automerge policy; the second
  requires every workflow to declare a top-level `permissions:` block. Both
  scripts are dependency-free.

## 1. Monitoring and alerts

### Workflows worth watching

| Workflow | Role | Blast radius if red |
|---|---|---|
| `reusable-ci-contract.yml` | The CI contract every consumer repo `uses:` | Every repo's build/test gate |
| `publish-flatpak.yml` | Publishes the tuna-os flatpak index to GHCR | Image publishing stops |
| `flatpak-tooling-drift-check.yml` | Weekly guard for `update-index.py` parity | Drift issue opened automatically |
| `renovate-policy-check.yml` | Enforces the automerge policy on `renovate.json` | Dependency bumps stop merging |
| `workflow-permissions-check.yml` | Enforces top-level `permissions:` blocks | Non-compliant workflows flagged |
| `ste-lint.yml` | Shared style/lint gate | Lint failures in callers |
| `drop-bot-review-requests.yml` | Drops bot review requests | Bot review noise |
| `reusable-scorecard.yml` | Security scorecard | Advisory only |

### What counts as a critical failure

- `publish-flatpak.yml` failing on `prod` — blocks image publishing for the
  whole org.
- `reusable-ci-contract.yml` failing — breaks every consumer's build/test.
- `flatpak-tooling-drift-check.yml` failing (see §3) — not an emergency, but it
  has been failing since **2026-08-17** and opens a new issue every week.

### Escalation path

1. Confirm the failure is in *this* repo's artifact (a shared workflow/action),
   not a consumer repo's own code. If a consumer is red because of its own
   change, the fix lives there.
2. If it is this repo's artifact, the fix is a PR to `main` here — there is no
   rollback, so make it correct the first time.
3. For an org-wide publishing outage, notify maintainers directly (the issue or
   PR is the public record; a maintainer channel is the fast path).

## 2. Common operational tasks

### 2.1 Updating ROADMAP-INDEX.md (the inventory)

`ROADMAP-INDEX.md` is the single-source-of-truth inventory of which active
repos have a per-repo `ROADMAP.md`. It is **currently maintained by hand** —
see `tuna-os#1295`, which is the open item to automate it. Until then:

1. List active, non-archived repos:
   ```bash
   gh repo list tuna-os --limit 200
   ```
2. For each, read its `ROADMAP.md` from its **default branch** (resolve the
   default branch per repo — never assume `main`; see §3).
3. Update the table and the "Last verified" date at the top.

The header records how it was built (`gh api …/contents/ROADMAP.md?ref=<default_branch>`
against every repo from `gh repo list`). Reproduce that to refresh.

### 2.2 Adding a new shared action to all repos

1. Write it under `.github/actions/<name>/` with an `action.yml`. If it takes
   inputs, route every input through `env:` in the script body — **never**
   `${{ }}` interpolation (see §3, "Don't put an input back into a script body").
2. Add a `README.md` documenting the inputs and their defaults — that block is
   the public API.
3. Copy the script into `project-starter/` if the shared script also exists
   there (the two `check-*.py` scripts are byte-identical copies today; keep
   them identical).
4. Announce it in a release note / maintainer message (§4) so repos can adopt.

### 2.3 Deprecating or removing a shared workflow

Because callers pin `@main`, removal is immediate and irreversible for anyone
already using it:

1. Post a deprecation notice (§4) with a removal date and the replacement.
2. After the window, open a PR that removes the workflow (or converts it to a
   no-op that errors with a pointer) and bump nothing else.
3. Confirm no repo `uses:` it before removing — grep the org if unsure.

### 2.4 Updating issue templates across the org

Templates live in `.github/ISSUE_TEMPLATE/` (`adoption.yml`, `bug.yml`,
`feature.yml`) and are inherited by every repo that does not ship its own copy.
Because they are consumed as YAML schemas, validate the YAML and confirm the
schema fields still match what consumer repos expect before merging.

## 3. Troubleshooting

### 3.1 flatpak-tooling-drift-check has been failing since 2026-08-17

The weekly `flatpak-tooling-drift-check.yml` **fails on every scheduled run**.
This is known and expected; it is not a regression:

- `dualcut` carries a `.github/scripts/update-index.py` that has **drifted**
  from the canonical copy.
- The other seven repos in its list no longer carry the file; the workflow
  reports that as a **warning**, not success.

Two things to know before "fixing" it:

- **The check's repo list is not the set of repos that carry a copy.** Today
  `flatpak-index`, `docs`, and `Tavern` each carry a copy that is **not** in the
  list and is not checked. And `tuna-os/flatpak-index`'s own copy describes
  *itself* as canonical — a second definition the check does not recognise.
- **The fix is migration, not editing the check.** Migrating a repo onto the
  reusable `publish-flatpak.yml` workflow (or the `publish-`/`update-flatpak-index`
  actions) removes the local copy rather than watching it drift. Do not tweak
  the check to stop failing — that hides real drift.

The canonical source is `tuna-os/flatpak-index/scripts/update-index.py`; the
`.github/actions/update-flatpak-index/update-index.py` here is a synced copy
(#123). If that copy drifts, re-sync it from the canonical source.

### 3.2 Don't put an input back into a script body

`update-flatpak-index/action.yml` routes every input through `env:` rather than
`${{ }}` interpolation, and that is load-bearing. **Actions substitutes
expressions into the script text before bash parses it**, so an interpolated
value is parsed as shell. Quoting narrows it and does not close it — a value
with a double quote ends the quoted region — and `--tags` is intentionally
unquoted so word-splitting spreads a multi-tag list into argparse's
`nargs="+"`. This action is the migration target for eight repos whose jobs
hold `packages: write` and `FLATPAK_INDEX_TOKEN`.

### 3.3 Debugging inherited ISSUE_TEMPLATE problems

If a consumer repo reports a broken or missing issue template:

1. Confirm whether the repo ships its own copy. Repos that inherit see changes
   here immediately; repos with their own copy are unaffected.
2. If it is inherited, the fix is here in `.github/ISSUE_TEMPLATE/`. Validate
   the YAML schema and confirm the fields still match what consumers expect.
3. Tell the consumer which upstream change touched their template.

### 3.4 Repos with non-standard default branches

`ROADMAP-INDEX.md` exists because the TunaOS ROADMAP drifted against a guess.
**`bootc-installer`, `fisherman`, `changelog-action`, `kde-build-meta` and
`mariner` default to something other than `main`.** Hardcoding `main` is how a
roadmap got stranded on the wrong branch. Always resolve each repo's default
branch (`gh repo view <repo> --json defaultBranchRef --jq '.defaultBranchRef.name'`)
rather than assuming.

### 3.5 Resolving Renovate automerge policy violations

`renovate.json` extends `local>tuna-os/.github` and is checked by
`renovate-policy-check.yml` against the automerge policy (#12). A syntactically
valid config can still automerge major and minor updates once `packageRules`
are layered — a schema validator alone would not catch it. When a violation
shows up:

```bash
python3 scripts/check-renovate-automerge-policy.py renovate.json
```

Fix the offending `packageRules` so major/minor updates are not auto-merged,
re-run the check until it prints `OK`, and confirm the script is still
byte-identical to `project-starter/scripts/check-renovate-automerge-policy.py`.

## 4. Communication protocols

### Notifying maintainers of breaking changes

Any change to a public API — a `publish-flatpak.yml` input, an action's
`inputs:` block, a shared workflow's behaviour, or a shared template — is a
breaking change for every consumer. Before merging:

1. State the blast radius explicitly in the PR body (which paths, which
   consumers).
2. Post a maintainer notice naming the change, the effective date, and the
   migration path.

### Providing deprecation notices for changed patterns

When a pattern is deprecated (a workflow, an action, a template field):

1. Announce the deprecation and the sunset date in advance.
2. Keep the old path working until the window elapses.
3. Remove it in a follow-up PR with a clear pointer for affected repos.

Because there is no rollback, the notice always precedes the change.

---

*Sources: `AGENTS.md`, `CONTRIBUTING.md`, `ROADMAP-INDEX.md`, and the
`flatpak-tooling-drift-check.yml`, `renovate-policy-check.yml`, and
`workflow-permissions-check.yml` workflows. See `tuna-os/.github#266`.*

— hive: backend=omp model=lab-worker/ornith
