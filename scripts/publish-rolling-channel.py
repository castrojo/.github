#!/usr/bin/env python3
"""Decide what the rolling Flatpak channel a publish-flatpak.yml run writes.

The rolling channel -- the arch-independent ``:latest`` image tag and the
central Flatpak index -- is gated behind prod promotion (``promote-to-prod.yml``):
a ``main`` commit reaches it only after it has fast-forwarded ``prod`` past the
Flatpak CI build. A release-tag dispatch of this reusable workflow --
``release.yml`` runs it at ``refs/tags/*`` -- must not move that channel: it
would let a commit that has not been promoted overwrite ``:latest`` and the
index, bypassing the gate (tuna-os/Tavern#195).

``rolling_channel_writes()`` is the whole contract. It is the single place that
says which writes are rolling-channel writes (and so are skipped on a release
tag), so the workflow's inline ``:latest`` push and central-index step stay in
lockstep with it. The version-qualified ``<tag>-<arch>`` image and the per-arch
``:latest-<arch>`` tag are release/per-arch artifacts, not the rolling channel,
so they are always pushed and are handled by the caller, not here.

Usage:
    publish-rolling-channel.py                 # reads $REF_INPUT (default: github.ref)
    REF_INPUT='refs/tags/v0.1.64' publish-rolling-channel.py \
        --arch x86_64 --primary x86_64
    publish-rolling-channel.py --ref 'refs/heads/prod' --arch aarch64 --primary x86_64

Exit codes:
    0  decision produced (printed as JSON to stdout; also written to
       $GITHUB_OUTPUT when set)
    1  the inputs are invalid (message on stderr)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional


def rolling_channel_writes(ref: str, arch: str, primary: str) -> dict:
    """Return the rolling-channel writes this run performs.

    `ref` is `github.ref` (e.g. ``refs/heads/prod`` or ``refs/tags/v0.1.64``);
    `arch` is the current matrix architecture; `primary` is the arch the
    unsuffixed ``:latest`` tracks (chosen by the arch-plan plan).

    Returns a dict:

        push_latest   whether to write the rolling ``:latest`` tag -- only on a
                      non-tag ref, and only from the primary-arch instance, so it
                      never races the other matrix instances
        update_index  whether to update the central index -- only on a non-tag
                      ref, because the index serves ``:latest``

    On a release tag both rolling-channel writes are skipped; the
    version-qualified ``<tag>-<arch>`` image is still pushed by the caller.
    """
    is_tag = ref.startswith("refs/tags/")
    return {
        "push_latest": (not is_tag) and arch == primary,
        "update_index": not is_tag,
    }


def _emit_outputs(decision: dict) -> None:
    """Write the decision to $GITHUB_OUTPUT for the workflow's steps.

    Single-line `key=value` pairs so the values round-trip through the
    workflow's `if:` expressions without a heredoc.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"push_latest={int(decision['push_latest'])}\n")
        fh.write(f"update_index={int(decision['update_index'])}\n")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ref = os.environ.get("REF_INPUT", os.environ.get("github_ref", ""))
    arch = os.environ.get("ARCH", "")
    primary = os.environ.get("PRIMARY", "")

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--ref", "--ref="):
            ref = argv[i + 1] if "=" not in arg else arg.split("=", 1)[1]
            i += 2
        elif arg == "--arch":
            arch = argv[i + 1]
            i += 2
        elif arg == "--primary":
            primary = argv[i + 1]
            i += 2
        else:
            print(f"ERROR: unknown argument {arg}", file=sys.stderr)
            return 1

    try:
        decision = rolling_channel_writes(ref, arch, primary)
    except Exception as exc:  # noqa: BLE001 - surface any bad input as exit 1
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(decision, separators=(",", ":")))
    _emit_outputs(decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
