# Claude Code in CI (`@claude` in PR comments)

`.github/workflows/claude.yml` wakes Claude Code when someone writes `@claude`
in a PR comment, a PR review, a review comment, or an issue. It is separate from
`tests.yml`, which runs the suite on every PR without being asked.

## Setup — needs a repository ADMIN

Neither step can be done with WRITE access. On `22abad/UN-DigitalTrade-AI-Mapper-private`
that means Dong has to do both, or grant admin temporarily.

**1. Install the Claude GitHub App**

<https://github.com/apps/claude> → install on this repository only.

It requests Contents / Issues / Pull requests — all Read & write. Those are what
let Claude push a fix to a PR branch and reply in the thread; the workflow's
`permissions:` block cannot substitute for them.

**2. Add the `ANTHROPIC_API_KEY` secret**

Settings → Secrets and variables → Actions → New repository secret.

Name it exactly `ANTHROPIC_API_KEY`. Get the key from
<https://console.anthropic.com>. This is a **separate bill** from the DeepSeek
key in `.env` — it is Anthropic API spend, not covered by anything the pipeline
already pays for.

There is an interactive alternative to both steps: run `/install-github-app`
in a Claude Code terminal from an admin account. It installs the app and writes
the workflow and secret for you. We already have the workflow, so if you use it,
choose the app-install step and skip the workflow it offers, or it will overwrite
`claude.yml` with the generic template and lose the project-specific prompt.

## Verifying it works

Open any PR and comment `@claude what does providers/base.py::_get_recent_corrections do?`.
A run should appear under Actions → "Claude Code" within a few seconds. If
nothing happens, in order of likelihood:

- the App is not installed (most common),
- `ANTHROPIC_API_KEY` is missing or invalid,
- you wrote `/claude` instead of `@claude`,
- the commenter lacks write access — see below.

## Who can trigger it

**Only users with write access to the repository.** That check is enforced by
`claude-code-action` itself, not by this workflow, and it is the main thing
standing between a PR comment and arbitrary code execution on our runner. Bots
are refused by default.

Do not "fix" a non-triggering comment by adding `pull_request_target` or by
loosening the `if:` condition. `pull_request_target` runs with repository
secrets available against a fork's code, which is the classic way to leak an API
key. Read
<https://github.com/anthropics/claude-code-action/blob/main/docs/security.md>
before changing the trigger surface.

Comment bodies from outside contributors are untrusted input. The action strips
some obfuscation (HTML comments, invisible characters) but the upstream guidance
is still to read the raw comment yourself before letting Claude act on it.

## What it costs

Two meters run at once:

- **GitHub Actions minutes** — bounded by `timeout-minutes: 30` on the job.
- **Anthropic API tokens** — bounded by `--max-turns 20` in `claude_args`.

`concurrency` is keyed per issue/PR with `cancel-in-progress: false`, so a second
`@claude` in the same thread queues instead of racing. Cancelling mid-run is
deliberately not done: unlike a test job, a half-killed agent can leave a
partial commit on the branch.

The model is pinned to `claude-sonnet-5`. Raise it to `claude-opus-5` in
`claude_args` for genuinely hard problems, but that is a real cost multiplier and
should not be the default for "explain this function".

## What Claude is allowed to run

`--allowedTools` restricts Bash to pytest, git read commands, `rg`, and `ls`.
It deliberately cannot run `main.py` or `scripts/rlvr_measure.py --with-llm`,
because both make billed provider calls — CI has no budget line for the agent
spending the extraction budget. The offline measurement is free and permitted.

The job installs `ai-service/requirements-ci.txt` (not the full
`requirements.txt`) so the suite can actually run. That skips torch and
playwright, which this job has no use for, and matches exactly what `tests.yml`
proves green.

`DISCOVERY_REGISTRY_BACKEND=file` is set and there is no database or live
provider in the runner. Tests needing either are expected to **skip**. If Claude
ever reports it "fixed" such a test, read that diff carefully.

## Relationship to CLAUDE.md

`CLAUDE.md` is picked up automatically from the repo root, so the standing rules
apply without being restated in the workflow. The `prompt:` block adds only
CI-specific constraints: no billed calls, no fabrication, tests green in the same
commit as a code change.
