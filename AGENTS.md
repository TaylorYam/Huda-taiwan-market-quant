# AI Development Guide

These instructions apply to coding agents and human contributors. Follow the repository's explicit task request when it narrows or extends this guide.

## Before changing files

1. Check the current branch and working tree. For normal project work, start from an up-to-date `main` and create a task branch or worktree before editing.
2. Read the linked GitHub issue when one is provided. If the request is unclear, establish its goal and acceptance criteria before implementation.
3. Read `README.md`, `docs/architecture.md`, and any relevant architecture decision records. Inspect the existing implementation and tests that relate to the change.
4. For substantial work, explain the understood outcome, likely files, approach, risks, and validation before editing. Follow any approval boundary the user explicitly sets.

## GitHub-first workflow

Keep `main` as the stable integration branch. For planned work, follow:

`Issue → branch or worktree → plan → implementation → validation → commit and push → pull request → review and CI → merge`

- Give branches descriptive names, for example `feat/export-report` or `fix/timezone-boundary`.
- Keep each change focused on its issue and record important user-visible or architectural tradeoffs in the pull request.
- Run the checks relevant to the changed code. Add or update tests when behavior changes, and report checks that could not be run.
- Link the issue in the pull request. Do not merge until required checks and review are complete.
- For a bootstrap repository with no established default branch, initialize the baseline as needed; use branches and pull requests for regular work after setup.

## Design and implementation

- Follow the existing architecture, naming, formatting, and dependency choices unless the task calls for changing them.
- Prefer the smallest coherent change that satisfies the acceptance criteria. Avoid unrelated refactors and dependencies.
- Update documentation when behavior, setup, or interfaces change.
- Record significant, long-lived architecture choices in `docs/adr/` using the format described there.

## Secrets and local data

- Keep credentials, access tokens, private keys, passwords, and populated `.env` files out of Git and out of logs or examples.
- Put only variable names and safe placeholder values in `.env.example`; obtain real secrets through the project's approved secret store or local environment.
- Keep generated runtime data, caches, build output, and machine-specific configuration out of commits unless the project explicitly treats an artifact as source.
- If a secret is found in the working tree or Git history, stop and report it; do not copy it into another file or repeat it in a message.

## Completion

Before handing work back, review the diff, run applicable validation, and summarize the change, test results, and any remaining limitation. Leave unrelated user changes untouched.
