# git hooks (tracked)

This directory is the repo's active hooks directory (`git config
core.hooksPath githooks`). Keeping hooks under version control means every
clone gets the same checks for free.

## What's here

| Hook          | What it does                                                                                  |
|---------------|-----------------------------------------------------------------------------------------------|
| `pre-commit`  | Runs `ruff check`, the full `pytest` suite, and the agentskills.io spec validator. Fail-fast. |
| `commit-msg`  | Enforces [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) on line 1.    |

Both are POSIX `sh` — no bashisms — so they run identically on macOS, Linux,
and CI.

## Activating hooks on a fresh clone

`core.hooksPath` is **not** auto-set by `git clone`, so the hooks aren't
active until you opt in. From the repo root:

```sh
git config core.hooksPath githooks
```

(That command is documented in the top-level `README.md` so first-time
cloners see it.)

To verify:

```sh
git config --get core.hooksPath    # should print: githooks
```

## Bypass

Emergencies only, never on shared branches:

```sh
git commit --no-verify ...
```

## Editing

Edit the scripts in this directory; they take effect immediately (no install
step). Keep them POSIX-compatible: no `[[ ]]`, no arrays, no `function`
keyword. Use `command -v` instead of `which`.
