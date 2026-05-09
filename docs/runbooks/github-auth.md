# GitHub CLI Auth Source of Truth

This repository uses `gh` for GitHub CLI operations.

## What `gh` Uses

`gh auth status` is the authoritative check.

- When `gh` is authenticated, it should report the active account as logged in.
- `gh` prefers the stored credential source for the host, such as the local keyring.
- `GITHUB_PERSONAL_ACCESS_TOKEN` in shell startup is not used by `gh` unless it is explicitly mapped to `GH_TOKEN` or `GITHUB_TOKEN`.

## Recommended Setup

1. Keep the working `gh` keyring login as the primary auth source.
2. Remove any stale `GITHUB_PERSONAL_ACCESS_TOKEN` export from shell startup if it is only confusing the environment.
3. Use `GH_TOKEN` or `GITHUB_TOKEN` only for scripts that need an explicit token in the process environment.

## Verification

Run:

```bash
gh auth status -h github.com
```

Expected result:

- `Logged in to github.com`
- `Active account: true`
- A valid token source, ideally `keyring`
