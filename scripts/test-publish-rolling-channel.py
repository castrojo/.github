#!/usr/bin/env python3
"""Pin the contract enforced by publish-rolling-channel.py.

The reusable publish-flatpak.yml publishes image tags for whatever its callers
dispatch, but the arch-independent ``:latest`` tag and the central Flatpak index
form the *rolling* channel: they track the newest promoted build. That channel
is gated behind prod promotion (promote-to-prod.yml), yet a release-tag dispatch
of this workflow (release.yml runs it at ``refs/tags/*``) reaches the publish
job at the tag and, before this contract was pinned, pushed ``:latest`` and
updated the index unconditionally -- letting an un-promoted commit overwrite the
rolling channel and bypass the gate (tuna-os/Tavern#195).

publish-rolling-channel.py is the single place that decides which writes are
rolling-channel writes; this file pins that decision so it cannot silently widen
again: a tag run must push neither ``:latest`` nor an index entry, a prod run
must push ``:latest`` only from the primary arch, and both must always update
the index. The version-qualified ``<tag>-<arch>`` image and the per-arch
``:latest-<arch>`` tag are release artifacts, not the rolling channel, so they
are out of scope here.

Plain python3, no test framework -- matches how scripts/ is already run in CI.
"""

from __future__ import annotations

import importlib.util
import pathlib

_src = pathlib.Path(__file__).with_name("publish-rolling-channel.py")
_spec = importlib.util.spec_from_file_location("publish_rolling_channel", _src)
publish_rolling_channel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish_rolling_channel)


# (name, ref, arch, primary, expected) -- expected is the full rolling-channel
# decision dict the run must produce.
CASES: list[tuple[str, str, str, str, dict]] = [
    (
        "a prod (heads/prod) run from the primary arch pushes :latest and indexes",
        "refs/heads/prod",
        "x86_64",
        "x86_64",
        {"push_latest": True, "update_index": True},
    ),
    (
        "a main run (the prod path) from the primary arch pushes :latest and indexes",
        "refs/heads/main",
        "x86_64",
        "x86_64",
        {"push_latest": True, "update_index": True},
    ),
    (
        "a prod run never pushes :latest from a non-primary arch",
        "refs/heads/prod",
        "aarch64",
        "x86_64",
        {"push_latest": False, "update_index": True},
    ),
    (
        "a prod run still updates the index from a non-primary arch",
        "refs/heads/prod",
        "aarch64",
        "x86_64",
        {"push_latest": False, "update_index": True},
    ),
    (
        "a release-tag run never pushes :latest (the #195 fix), primary arch",
        "refs/tags/v0.1.64",
        "x86_64",
        "x86_64",
        {"push_latest": False, "update_index": False},
    ),
    (
        "a release-tag run never updates the index (the #195 fix), non-primary arch",
        "refs/tags/v0.1.64",
        "aarch64",
        "x86_64",
        {"push_latest": False, "update_index": False},
    ),
    (
        "an aarch64-primary prod run publishes :latest from aarch64",
        "refs/heads/prod",
        "aarch64",
        "aarch64",
        {"push_latest": True, "update_index": True},
    ),
]


def _run_case(name, ref, arch, primary, expected):
    got = publish_rolling_channel.rolling_channel_writes(ref, arch, primary)
    if got != expected:
        return f"{name}: decision {got} != expected {expected}"
    return None


def main() -> int:
    failures = []
    for name, ref, arch, primary, expected in CASES:
        problem = _run_case(name, ref, arch, primary, expected)
        if problem:
            failures.append(problem)

    # The invariant the #195 fix protects: on ANY tag ref, neither rolling
    # channel write happens, regardless of arch or primary. A caller could
    # otherwise special-case one arch and let it through.
    for ref in ("refs/tags/v0.1.64", "refs/tags/v0.1.64-arm64v9"):
        for arch, primary in (("x86_64", "x86_64"), ("aarch64", "x86_64"), ("aarch64", "aarch64")):
            got = publish_rolling_channel.rolling_channel_writes(ref, arch, primary)
            if got != {"push_latest": False, "update_index": False}:
                failures.append(
                    f"tag {ref} arch {arch}: rolling channel not fully skipped, got {got}"
                )

    if failures:
        print("FAIL: publish-rolling-channel contract regressed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {len(CASES)} contract cases + tag-skip invariant pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
