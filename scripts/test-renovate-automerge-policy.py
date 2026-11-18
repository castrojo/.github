#!/usr/bin/env python3
"""Pin the boundary enforced by check-renovate-automerge-policy.py.

The checker is a security gate, and its blocked set was narrowed from
{major, minor} to {major} when the fleet moved to automerged minor bumps.
That is exactly the kind of loosening that erodes further by accident, so the
line is pinned here: minor must pass, major must fail, and the scoping rules
that stop a narrow override from cancelling a broad bypass must still hold.

Plain python3, no test framework -- matches how scripts/ is already run in CI.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_src = pathlib.Path(__file__).with_name("check-renovate-automerge-policy.py")
_spec = importlib.util.spec_from_file_location("policy", _src)
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)

CASES: list[tuple[str, dict, bool]] = [
    # (name, config, expect_violation)
    (
        "minor+patch automerge is allowed (the whole point of the change)",
        {"packageRules": [{"matchUpdateTypes": ["minor", "patch", "pin", "pinDigest", "digest"], "automerge": True}]},
        False,
    ),
    (
        "explicit major automerge is still blocked",
        {"packageRules": [{"matchUpdateTypes": ["major"], "automerge": True}]},
        True,
    ),
    (
        "top-level automerge:true is still blocked (covers major)",
        {"automerge": True},
        True,
    ),
    (
        "a rule with no matchUpdateTypes applies to major, so it is blocked",
        {"packageRules": [{"automerge": True}]},
        True,
    ),
    (
        "explicit major:false alongside minor:true is compliant",
        {
            "packageRules": [
                {"matchUpdateTypes": ["minor", "patch"], "automerge": True},
                {"matchUpdateTypes": ["major"], "automerge": False},
            ]
        },
        False,
    ),
    (
        "a package-scoped major automerge is still caught",
        {"packageRules": [{"matchPackageNames": ["left-pad"], "matchUpdateTypes": ["major"], "automerge": True}]},
        True,
    ),
    (
        "a narrow major:false must NOT cancel an earlier broad bypass (protota regression)",
        {
            "packageRules": [
                {"automerge": True},
                {"matchDatasources": ["docker"], "matchUpdateTypes": ["major"], "automerge": False},
            ]
        },
        True,
    ),
    (
        "minor automerge scoped to one package is allowed",
        {"packageRules": [{"matchPackageNames": ["serde"], "matchUpdateTypes": ["minor"], "automerge": True}]},
        False,
    ),
]

# Public registries whose releases the shared preset must not take on the day
# of publication. Renovate reads a release timestamp from each of them.
COOLDOWN_DATASOURCES = ("npm", "pypi", "crate")


def main() -> int:
    failures = []

    repo_root = pathlib.Path(__file__).parents[1]
    starter_checker = repo_root / "project-starter/scripts/check-renovate-automerge-policy.py"
    if _src.read_bytes() != starter_checker.read_bytes():
        failures.append(
            "  - project-starter policy checker differs from the canonical "
            "scripts/check-renovate-automerge-policy.py"
        )

    for name, config, expect_violation in CASES:
        got = policy.check(config)
        if bool(got) != expect_violation:
            failures.append(
                f"  - {name}\n      expected {'a violation' if expect_violation else 'no violation'}, got {got or 'none'}"
            )

    # The shipped preset every repo extends must itself be compliant.
    import json

    preset = json.loads((repo_root / "default.json").read_text(encoding="utf-8"))
    if policy.check(preset):
        failures.append(f"  - default.json (the shared preset) violates the policy: {policy.check(preset)}")

    # Minor and patch updates merge themselves, so the preset must hold a new
    # registry release back before Renovate raises it. Only a rule that
    # matches on the datasource alone counts: a rule with one more matcher
    # covers some of that registry's packages, not all of them.
    waited = {
        datasource
        for rule in preset.get("packageRules", [])
        if rule.get("minimumReleaseAge") not in (None, "", "0 days")
        and set(rule) <= {"description", "matchDatasources", "minimumReleaseAge"}
        for datasource in rule.get("matchDatasources", [])
    }
    for datasource in COOLDOWN_DATASOURCES:
        if datasource not in waited:
            failures.append(
                f"  - default.json has no minimumReleaseAge rule for the '{datasource}' "
                "datasource: its minor and patch updates would merge on the day of release"
            )

    if failures:
        print("FAIL: renovate automerge policy checker regressed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"OK: project-starter checker is synchronized; {len(CASES)} policy "
        "cases + default.json behave as pinned; default.json waits before "
        f"taking {', '.join(COOLDOWN_DATASOURCES)} releases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
