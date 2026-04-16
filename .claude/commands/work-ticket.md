# /work-ticket — implement one ticket end-to-end

You are picking up a single ticket from the GitHub Project and taking it all
the way to an open PR with the ticket moved to "In Review". Do not skip steps.
Do not batch multiple tickets in one run.

## Input

The user invokes this command with a ticket key:

```
/work-ticket T-003
```

If no key is given, ask which one. Never guess.

## Preconditions you MUST verify before writing any code

1. Working tree is clean: `git status --porcelain` returns empty.
   - If dirty, stop and tell the user. Do not stash.
2. You are on `main` (or the repo's default branch) and it's up to date:
   `git fetch origin && git status -uno` shows "up to date".
3. `sync-report.json` exists at the repo root or under `02-tasks/`.
   It contains the `T-XXX -> issue #N` mapping. If missing, stop and say so.
4. `gh auth status` succeeds.

## Step 1 — Load the ticket

Resolve the issue number from `sync-report.json`:

```bash
ISSUE=$(jq -r ".mapping[\"$KEY\"]" sync-report.json)
```

Fetch the issue:

```bash
gh issue view "$ISSUE" --json number,title,body,labels,assignees,milestone,state
```

Read the body carefully. Extract:
- The description
- The **Acceptance criteria** checklist (these are your done-definition)
- The **Files likely touched** hints (a hint, not a contract)
- The **Blocked by** list (if any)

If any `Blocked by` issue is still open, STOP. Tell the user the ticket isn't
ready. Do not start work on a blocked ticket.

## Step 2 — Transition the ticket to "In Progress"

Use the helper in `scripts/project_status.sh` (it calls the GraphQL API):

```bash
scripts/project_status.sh "$KEY" "In Progress"
```

Leave a comment on the issue so there's an audit trail:

```bash
gh issue comment "$ISSUE" --body "🤖 Claude Code starting work on this ticket."
```

## Step 3 — Branch

Branch name convention: `<type>/<key>-<slug>` where:
- type is the primary label (`feat`, `fix`, `infra`, `docs`, `test`) derived from `type:*` label
- slug is a kebab-cased short form of the title, ≤ 40 chars

Example: `feat/T-003-sqlite-migrations-runner`

```bash
git checkout -b "$BRANCH"
```

## Step 4 — Plan before coding

Write the plan to yourself in scratch form (do NOT commit this file).
Cover:
- Which files you will add/modify (start from `Files likely touched`, adjust as needed).
- The public API shape (signatures, return types).
- Test cases you'll write FIRST, one per acceptance criterion.
- Any assumption you're making that isn't in the ticket.

If an assumption materially changes scope, pause and comment on the issue
asking the user to confirm before proceeding. Don't silently expand scope.

## Step 5 — Implement, test-first

1. Write the failing tests first, one per acceptance criterion.
2. Run them: they should fail for the right reason.
3. Implement the minimum code to make them pass.
4. Re-run the full suite: `pytest -q` (or the repo's documented test command).
5. Run the linters: `ruff check .` and `mypy` (if configured).
6. If any of (lint, type, test) fail, fix them. Do not push red.

Coverage requirement: if the ticket labels include `area:core` or
`area:storage`, target ≥ 90% coverage on the files you touched:

```bash
pytest --cov=pomo --cov-report=term-missing
```

## Step 6 — Commit

One logical commit per ticket is preferred. If the work genuinely needed
two (e.g. "schema migration" + "repository on top"), two is fine.

Conventional-commit format, with the ticket key in the footer:

```
feat(storage): add SQLite connection and migrations runner

Implements a get_connection() that applies pending SQL migrations from
pomo/storage/migrations/*.sql inside a schema_migrations table. WAL mode
and foreign_keys are enabled on every connection.

Refs: T-003
Closes: #<ISSUE_NUMBER>
```

Rules:
- `Closes: #N` goes in the **last** commit only.
- Use `Refs: T-KEY` in every commit so `git log --grep` works.
- Never commit secrets, local DB files, or `.venv`.

## Step 7 — Push & open PR

```bash
git push -u origin "$BRANCH"
gh pr create \
  --title "[$KEY] <same as issue title>" \
  --body-file .github/pr-body.md \
  --assignee @me \
  --label "ready-for-review"
```

The PR body template (`.github/pr-body.md`) should include:
- "Closes #N" on its own line
- A short summary (2–4 sentences)
- Checked-off acceptance criteria copied from the issue
- A "How I tested" section with actual commands run

## Step 8 — Transition ticket

```bash
scripts/project_status.sh "$KEY" "In Review"
gh issue comment "$ISSUE" --body "🤖 PR opened: <PR_URL>"
```

## Step 9 — Stop

Do NOT merge the PR. Do NOT move the ticket to Done. A human reviews and
merges. When the PR merges, GitHub's "Closes #N" will auto-close the issue;
the Project's built-in automation should move it to Done.

## Failure modes — what to do when things go wrong

- **Tests fail after implementation and you can't see why quickly:**
  Commit a WIP branch, push, open a draft PR, and comment on the issue with
  what you tried. Do not leave the ticket stuck in "In Progress" silently.

- **The ticket is under-specified:**
  Comment on the issue with the specific question. Move ticket back to
  `Ready` or `Blocked` (your judgment). Stop.

- **A dependency you need isn't declared in `pyproject.toml`:**
  Add it, justify it in the commit message, keep the dep list minimal.
  If it's a heavy dep (>10 MB or with native build requirements), stop and
  ask first.

- **You discovered a separate bug while doing the ticket:**
  Do NOT fix it in this PR. File a new issue with a reproducer. Keep this
  PR focused.

## Never do

- Force-push to `main`.
- Edit `sync-report.json` by hand.
- Create issues, labels, or milestones outside the sync pipeline.
- Close or merge PRs on behalf of the user.
- Add co-author trailers or promotional text to commits.
