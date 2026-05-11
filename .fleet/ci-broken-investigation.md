# CI Investigation Notes (Cannot Auto-Fix)

**Date:** 2026-05-11
**Branch:** `fix/ci-restore-green`
**Task:** MOT-31

## What's Failing

**Every GitHub Actions workflow run in this repo is failing** with the same
error, visible in the run annotations:

```
The job was not started because recent account payments have failed
or your spending limit needs to be increased. Please check the
'Billing & plans' section in your settings
```

This affects ALL workflows:

| Workflow | Latest Run ID | Conclusion |
|---|---|---|
| `release-please` | 25683196166 | failure |
| `release-please` | 25683127137 | failure |
| `release-please` | 25683062886 | failure |
| `release-please` | 25682009556 | failure |
| `release-please` | 25681966069 | failure |
| `Dependabot auto-merge` | 25682077123 | failure |

## Affected PRs

| PR | Branch | Status Check |
|---|---|---|
| #18 | `dependabot/pip/...5de19aa93e` | auto-merge: FAILURE |
| #14 | `dependabot/pip/...1b3191f6ff` | auto-merge: FAILURE |
| #13 | `dependabot/github_actions/...6d50401484` | auto-merge: FAILURE |

Every non-dependabot PR was merged via the merge queue before the billing
issue started. All open/closed dependabot PRs have failed since the billing
issue began.

## What I Tried

1. **Inspected all workflow files** (`.github/workflows/`):
   - `release-please.yml` — Google's release-please action
   - `dependabot-auto-merge.yml` — auto-merges dependabot patch updates
   - Both are standard templates; no code-level defects.

2. **Checked for missing env vars or secrets** in workflows — none are
   referenced; both use `${{ secrets.GITHUB_TOKEN }}` which is auto-injected.

3. **Verified repo contents**: ran `ruff check .` — found 37 linting errors
   (E401, F401, E701, F541, F841) across `abcd.py`, `agent.py`,
   `ollama_client.py`, `reddit_client.py`, `reporter.py`, `sharpener.py`,
   `x_client.py`. These are pre-existing style issues, not CI blockers.

4. **Confirmed billing error across all workflow types** — release-please
   (push-triggered) and dependabot-auto-merge (PR-triggered) both fail with
   the identical billing error.

## What Human Needs to Do (to unblock)

1. **Fix GitHub billing:**
   - Go to https://github.com/settings/billing (org owner) or
     https://github.com/account/settings/billing (personal account)
   - Verify the payment method is current and has sufficient funds
   - If on a free-tier plan with exhausted minutes, upgrade or wait for
     the billing cycle to reset

2. **After billing is restored**, re-run failed workflows:
   - For each failed dependabot PR, close and re-open the PR to
     re-trigger checks, or push an empty commit to the branch
   - For `main`, push a trivial commit or re-run the failed
     `release-please` runs via the GitHub UI

3. **Optionally (not a blocker), fix the 37 ruff linting errors** to keep
   the codebase healthy. These are all auto-fixable (`ruff check --fix`):
   - Split multi-import lines (E401)
   - Remove unused imports (F401)
   - Break one-liner conditionals into multi-line (E701)
   - Remove extraneous f-prefixes (F541)
   - Remove unused variable assignments (F841)

## Repo CI Readiness

- No test framework is configured (no `pytest`, `unittest`, or `test/` dir)
- No `ci.yml` workflow file exists — the only workflows are
  `release-please.yml` and `dependabot-auto-merge.yml`
- If a CI pipeline is desired, one should be added (e.g. run `ruff check`
  and any future tests on every PR)
