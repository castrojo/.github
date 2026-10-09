# Action Security: Safe Environment Variable Use

Guide for authors of composite and JS actions in this org. It covers one class
of bug that is easy to write and hard to see in review: letting an action
input become shell.

## The rule

Route every action input through the `env:` block of a `run:` step. Never
interpolate `${{ inputs.* }}` (or any other untrusted value) into the script
text of that step.

```yaml
# SAFE: the input is data, bound to a variable the shell expands later.
- shell: bash
  env:
    TAGS: ${{ inputs.tags }}
  run: |
    python3 update-index.py --tags "${TAGS}"

# UNSAFE: the input is substituted into the script text before the shell runs.
- shell: bash
  run: python3 update-index.py --tags ${{ inputs.tags }}
```

The rule applies only to a `run:` script body. `${{ }}` is still the correct
way to pass values to `with:` (another action), `if:`, `with:` on `uses:`, and
every other non-script context. Those contexts are never parsed as shell, so
interpolation there carries no injection risk. The danger is interpolation
*into executable script text*.

## Why interpolation is unsafe

Actions evaluates `${{ }}` expressions and substitutes their rendered value
directly into the script text *before* the shell parses it. The substituted
value is then parsed as shell — it becomes part of the command, not data
passed to it.

Given this step:

```yaml
- run: python3 update-index.py --tags ${{ inputs.tags }}
```

a caller that passes `tags: latest; touch /tmp/PWNED` renders the script as:

```sh
python3 update-index.py --tags latest; touch /tmp/PWNED
```

The shell runs two commands. The `touch` executes, creates the file, and the
step still exits 0 when the rest succeeds — so the injection looks clean in the
log. The same mechanism turns any input into remote code execution for anyone
who can supply it. This is exactly what the
`update-flatpak-index` action was migrated away from: its `--tags` argument was
interpolated, and the only fix that closed it was moving the value into `env:`.

## Why quoting does not fix it

Quoting narrows the surface but does not close it:

```yaml
- run: python3 update-index.py --tags "${{ inputs.tags }}"
```

A value that contains a double quote ends the quoted region and resumes shell
parsing inside it. A payload such as `x"; touch /tmp/PWNED; "` renders as:

```sh
python3 update-index.py --tags "x"; touch /tmp/PWNED; ""
```

The injected quote closes the string, the `;` starts a new command, and the
`touch` runs. Quoting is good hygiene, but it is not a boundary. The only
reliable boundary is keeping the value out of the script text entirely, which
`env:` provides.

## The fix: `env:` makes the value data

A variable expanded by the shell (`${TAGS}`) is resolved *after* the command
line is parsed. Whatever the value contains — spaces, semicolons, quotes — it
stays one argument and cannot change the command structure:

```yaml
- shell: bash
  env:
    TAGS: ${{ inputs.tags }}
  run: |
    python3 update-index.py --tags "${TAGS}"
```

The shell never sees the value as code. A `;` or `"` inside `TAGS` is data.

## Word splitting: do it deliberately, not by accident

Sometimes a step genuinely needs to turn one space-separated input into several
arguments — for example, passing a list of OCI tags to a script whose `--tags`
uses `nargs="+"`. Do the split explicitly with `read -ra`, then quote the
result so each element stays a single argument:

```bash
set -euo pipefail

read -ra tag_args <<<"$TAGS"
if [ "${#tag_args[@]}" -eq 0 ]; then
  echo "::error::tags input is empty" >&2
  exit 1
fi

python3 update-index.py --tags "${tag_args[@]}"
```

`read -ra` performs the split the multi-tag case needs; `"${tag_args[@]}"`
passes each tag as its own quoted argument. Leaving `${TAGS}` unquoted
(`--tags $TAGS`) happens to word-split on the common case, but it couples the
split to the caller's `IFS` and is the exact pattern that was exploitable here
before the migration — an unquoted expansion is still shell, and the split is
no longer visible where it is decided.

## Validate inputs before they reach the script

Treat every input as untrusted, and reject the ones you can recognise *after*
they are data. In `update-flatpak-index` each tag is checked against the OCI
tag grammar before the script runs, so a malformed input is a clear error here
instead of a stray argument:

```bash
for tag in "${tag_args[@]}"; do
  if ! [[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]]; then
    echo "::error::invalid OCI tag: $tag" >&2
    exit 1
  fi
done
```

Validation is a defence in depth: it does not replace routing the value through
`env:`, but it turns an injection that slips past into a loud, specific failure.

## Secrets and tokens

- Route tokens through `env:` like any other input. They are values, and keeping
  them out of the interpolated script text also keeps them out of the rendered
  step log.
- For git authentication, use header-based auth so the token never lands in
  `.git/config`, `git remote -v`, or process listings:

```bash
git -C "$INDEX_REPO" config --local http.extraheader \
  "AUTHORIZATION: basic $(printf 'x-access-token:%s' "$FLATPAK_INDEX_TOKEN" | base64 -w0)"
```

This is the pattern `publish-flatpak-index` uses to push the central index with
`FLATPAK_INDEX_TOKEN` — the token stays in an env var and a request header,
never in a URL or a config file that a later `git remote -v` would expose.

## Checklist

- [ ] Every `run:` step that takes inputs maps them via `env:`, not `${{ }}`.
- [ ] No `${{ inputs.* }}` (or other untrusted value) appears inside a `run:` script body.
- [ ] Values are quoted when passed as arguments (`"${VAR}"`).
- [ ] A value that must become several arguments is split with `read -ra`, then the expansion is quoted.
- [ ] Untrusted inputs are validated before they reach a command.
- [ ] Secrets and tokens go through `env:`; git auth uses header-based tokens.

## References

- `.github/actions/update-flatpak-index/action.yml` — the migration target.
  Routes all inputs through `env:`, splits `tags` with `read -ra`, and validates
  each tag against the OCI grammar.
- `.github/actions/publish-flatpak-index/action.yml` — token handling and
  header-based git auth for pushing the central index.
- `.github/actions/ste-lint/action.yml` — shows the safe split: `${{ }}` for
  `with:` (setup-node) and `env:` for the `run:` step.
- `AGENTS.md` — the `update-flatpak-index` injection write-up this guide expands.
