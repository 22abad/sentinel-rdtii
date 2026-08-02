# Project skills

Vendored Claude Code Agent Skills. Loaded automatically at the start of a
Claude Code session; invoke by name (e.g. the `tdd` skill triggers on
"red-green-refactor" / test-first work).

- **tdd**, **code-review**, **diagnosing-bugs** — from Matt Pocock's public
  skills collection (https://github.com/mattpocock/skills, MIT). tdd enforces
  red-before-green (failing test first, then minimal implementation) and
  vertical slices; code-review runs Standards + Spec passes; diagnosing-bugs is
  the hard-bug diagnosis loop.

Add project-specific skills as `.claude/skills/<name>/SKILL.md` (frontmatter:
`name` + `description`; the description says WHEN to trigger).
