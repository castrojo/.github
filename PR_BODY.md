## Summary

The reusable `.github/workflows/publish-flatpak.yml` workflow had no `permissions` block, so every job inherited whatever the caller granted. Callers run this with `secrets: inherit`, so a caller that set broad permissions leaked that scope into the build job too, and there was no way to audit what the workflow actually requires.

This adds a top-level `contents: read` baseline plus job-level grants scoped to what each job genuinely does:

- **build-oci** inherits `contents: read` (actions/checkout, the flatpak build, and upload-artifact need no write scope)
- **publish** gets `packages: write` for the GHCR `skopeo` push; the central-index write uses `FLATPAK_INDEX_TOKEN`, not `GITHUB_TOKEN`
- **release-bundles** gets `contents: write` for `gh release upload`

No inputs, defaults, or the `workflow_call` / `uses:` path changed, so existing callers are unaffected.

## Finding #2 (secrets)

The workflow already scopes its only named secret to `FLATPAK_INDEX_TOKEN` (it does not declare `secrets: inherit`), and the build job declares and uses no secret. Splitting build vs publish into two reusable workflows -- so the build side declares no secrets at all -- is a larger change that requires updating every external caller, so it is left as a follow-up rather than shipped here.

## Testing

- `yaml.safe_load` parses the workflow.
- `actionlint v1.7.7` reports no errors.
- Permissions verified against each job's actual steps: only the GHCR push needs `packages: write`, only `gh release upload` needs `contents: write`, and everything else is read-only.

Fixes tuna-os/.github#139

— hive: backend=omp model=lab-worker/ornith
