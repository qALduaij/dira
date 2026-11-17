# AGENTS.md

Working rules for AI coding agents in this project: Codex, Antigravity, Claude
Code (through `CLAUDE.md`) and any other tool that reads `AGENTS.md`.

## Project

<!-- Fill in at project start. Delete lines that don't apply. -->
- **What it is:** TODO, one sentence
- **Stack:** TODO, language, framework and versions
- **Install:** `TODO`
- **Run:** `TODO`
- **Test:** `TODO`. Run it before saying anything works.
- **Lint / format:** `TODO`
- **Off limits:** TODO, files agents must not edit (generated code, vendored code, secrets)

## How to work

Three skill packs are installed globally. They have this order of authority:

1. **superpowers decides the process:** how work moves from idea to merge.
2. **ponytail decides the size:** how much code each step gets.
3. **REA is a specialist:** only for evidence that lives in shipped software.

If a skill named here isn't available in your tool, read its `SKILL.md` from
the source repo and follow it anyway:
[superpowers](https://github.com/Q-alduaij/superpowers/tree/main/skills),
[ponytail](https://github.com/Q-alduaij/ponytail5/tree/main/skills),
[REA](https://github.com/morluto/rea/tree/main/.agents/skills/reverse-engineer-anything).

### Process (superpowers)

Before each task, check whether a skill applies. If it does, use it.

| Situation | Skill |
|---|---|
| New feature, behavior change, anything creative | `brainstorming` first. Small change: agree in chat. Bigger: a short design doc in `docs/`. |
| Approved design with several steps | `writing-plans`, then `subagent-driven-development` or `executing-plans` |
| Writing or changing code | `test-driven-development`: failing test, watch it fail, minimal code, watch it pass |
| Bug, failing test, odd behavior | `systematic-debugging`: find the root cause before changing code |
| About to say "done", "fixed" or "passing" | `verification-before-completion`: run the check and show the output |
| Work that needs isolation | `using-git-worktrees` |
| Task finished, before merge | `requesting-code-review`, then `finishing-a-development-branch` |
| Receiving review feedback | `receiving-code-review`: verify each point, don't just agree |

Scale the process to the task. A one-line fix needs no design doc, but it
still needs a test if it has logic, and a verification run.

### Size (ponytail)

Default level: **full**. For each change, take the first option that fully works:

1. Does it need to exist at all?
2. Is it already in this codebase?
3. Does the standard library do it?
4. Does a native platform feature cover it?
5. Does an already-installed dependency do it?
6. Can it be one line?
7. Only then: the minimum new code.

- Read the code the change touches first. Lazy about the solution, never about reading.
- Ask before adding any dependency, and never add one for what a few lines can do.
- No speculative abstractions, options or configuration nobody asked for.
- Ponytail never cancels tests or verification: small code, still tested.
- Mark deliberate shortcuts with a `shortcut:` comment saying what was skipped
  and when it will matter (`ponytail-debt` collects them).
- End each reply with what you skipped or didn't check, and any risk.

Reviews: `ponytail-review` for a change, `ponytail-audit` for the whole repo.

### Reverse engineering (REA)

Use the `reverse-engineer-anything` skill and the `rea` MCP tools only when the
answer depends on shipped software without source: a binary, app bundle,
Electron/ASAR, APK, firmware, or a live website's runtime behavior. For code in
this repo, use the normal tools.

- Only analyze software the user owns or is allowed to analyze.
- Give the evidence and its limits with every conclusion.
- When rebuilding a feature you studied, write new code from your own
  understanding. Don't paste decompiled code into this project.

### Library docs

For questions about a library, framework, SDK, API or CLI, fetch current docs
with Context7 (`resolve-library-id`, then `query-docs`) before answering from
memory. If that fails, use the official docs.

## Rules

- **Git:** work on a branch, with small commits and clear messages. Never push,
  force-push, merge to the main branch or rewrite history without asking.
- **Secrets:** never commit keys, tokens or `.env` files. Keep placeholders in `.env.example`.
- **Destructive actions** (deleting data, dropping tables, `rm -rf`,
  migrations on real data): ask first.
- **Unclear task:** if a wrong guess would be costly, ask one specific question.
- **Honest reports:** if tests fail or a step was skipped, say so and show the output.
- **Keep docs current:** when you change how the project is installed, run or
  tested, update the Project section above and the README.
