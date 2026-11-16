# Organization Enablement Roadmap

**Last updated**: 2026-10-16 | **Maintainer**: TunaOS organization maintainers

## Mission

Make `tuna-os/.github` the reliable organization-wide front door for
contributors and maintainers: shared community-health guidance should work for
every repository, while portfolio-level planning inventories should stay
current enough to support prioritization.

## Current Status

The repository provides shared contribution and security guidance, issue and
pull-request templates, a reusable project starter, and an org-wide roadmap
inventory. Most authorized repositories inherit its issue forms, so changes
here affect the contributor experience across the portfolio.

### Priorities

| Priority | Item | Tracking | Status |
|---|---|---|---|
| P0 | Make inherited issue forms repository-neutral and keep image-specific fields local to `tuna-os/tunaOS` | #32 (closed by #86) | Done (merged #86) — shared `bug.yml` and `feature.yml` collect repository-neutral context and point OS-image reports to `tuna-os/tunaOS` |
| P1 | Automate default-branch-aware refreshes of `ROADMAP-INDEX.md` | #110, #137 (supersedes closed tuna-os/tunaOS#1295) | Done (merged #211) — weekly `roadmap-index-automation.yml` runs `scripts/roadmap-index.py --write` against each active repo's default branch and opens a PR on drift |
| P1 | Complete adoption of the canonical Flatpak index action and retire the interim copy-drift guard | #128, #271 (supersedes closed tuna-os/tunaOS#1183, #37) | In progress — `Tavern`, `dualcut`, `mandelbrot`, `gtk-office-suite`, `bootc-installer`, and `mariner` are on shared tooling (verified #271); `tuna-os/blueshell` has since migrated (tuna-os/blueshell#85); `tuna-os/docs` still carries a drifted local `update-index.py` copy (tuna-os/docs#448). `flatpak-tooling-drift-check.yml` has been manually disabled since 2026-10-15, after its last scheduled run (2026-10-12, #128) failed on that drift; re-enable it once tuna-os/docs#448 lands |
| P1 | Give inherited planning artifacts a named human owner: remove automation bylines from the starter template and sweep the 37 committed files across 19 repositories that inherited them | #54 | In progress — starter template and this repo's `ROADMAP.md` fixed (merged #55); cross-repo sweep across the remaining 18 repositories still open |
| P2 | Define an owner and review cadence for org-level community-health files | #32 | Proposed (#32 closed via #86 on template neutrality; separate tracker needed for formal community-health file ownership) |

## 2026 Q3 Exit Goals

| Goal | Success measure | Tracking |
|---|---|---|
| Correct the shared issue-entry funnel | Shared forms collect repository-neutral context; image-specific forms live in `tuna-os/tunaOS`; representative app, library, installer, and CI repositories are verified | #32 (closed by #86) |
| Make portfolio planning observable | Maintain the verified 36/40 active-repository baseline; resolve the superseded `kde-build-meta` lifecycle; automation work is separately scoped | #52, #110, #211 (supersedes closed tuna-os/tunaOS#1295; `tuna-os/kde-build-meta` removed) |

### Q3 Exit Verification (as of 2026-10-16)

Q3 closed on 2026-09-30. The table below checks each exit goal against live repository and issue state:

| Goal | Verified outcome |
|---|---|
| Correct the shared issue-entry funnel | **Met post-Q3 (2026-10-15).** Missed the 2026-09-30 exit date while #32 remained open, then completed when PR #86 merged on 2026-10-15, making `.github/ISSUE_TEMPLATE/bug.yml` and `feature.yml` repository-neutral and directing OS-image issues to `tuna-os/tunaOS`. |
| Make portfolio planning observable | **Met (automation completed post-Q3 on 2026-10-15).** `ROADMAP-INDEX.md` scope was corrected from 36/37 to 36/40 on 2026-09-02 (#52, #53) when `spindle`, `blueshell`, and `hive` were added (all three now have `ROADMAP.md` on their default branches; live `scripts/roadmap-index.py --diff` reports 38/45 active repositories). Superseded `tuna-os/kde-build-meta` has been removed from the organization (HTTP 404), resolving its retirement lifecycle. `tuna-os/tunaOS#1295` closed 2026-09-24 as misfiled, and scheduled default-branch-aware automation landed here in PR #211 (`scripts/roadmap-index.py` + `roadmap-index-automation.yml`). |

## 2026 Q4 Goals

| Goal | Success measure | Tracking |
|---|---|---|
| Prevent roadmap inventory drift | A scheduled, default-branch-aware check proposes reviewable updates when repository coverage changes | #110, #137 (implemented in #211; supersedes closed tuna-os/tunaOS#1295) |
| Reduce duplicated release tooling | Remaining callers (`tuna-os/blueshell` and `tuna-os/docs`, verified in #271) migrate to the shared Flatpak tooling and `flatpak-tooling-drift-check.yml` can be retired | #128, #271 (supersedes closed tuna-os/tunaOS#1183, #37) |
| Measure contributor-funnel health | Quarterly review records issue-form overrides, misrouted reports, and first-response outcomes following the repository-neutral template rollout (#86) | #32 (closed by #86; Q4 review pending) |
| Make governance documents attributable to people | No committed file in the portfolio attributes org policy to an automation agent; every roadmap names a human or team owner | #54 (starter template fixed in #55; 18-repo sweep open) |

## Decision Principles

1. Shared defaults must be useful to every repository that inherits them.
2. Product-specific questions belong in local templates, not the org fallback.
3. Portfolio inventories must query each repository's actual default branch.
4. Scheduled automation should propose reviewable changes rather than silently
   rewrite planning artifacts.

## Review Cadence

Review this roadmap at each quarter boundary and whenever a shared template or
project-starter contract changes. Every roadmap item should link to an issue
with an owner, acceptance criteria, and evidence of completion before its
status is marked done.

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). Planning changes should explain which
repositories inherit the affected org-level default and link the tracking
issue used to coordinate any repository-local follow-up.

---
*Maintained as an organization-level planning artifact. Changes land by PR against this
file; see [CONTRIBUTING.md](CONTRIBUTING.md).*
