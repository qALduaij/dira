# Master Instructions — Agent Kit

The one place that explains how my AI coding setup works across Claude Code,
Codex and Antigravity: what is installed, where each tool reads it, how to set
up a machine, and how to start a new project.

## What's in the kit

| File | Purpose | Who reads it |
|---|---|---|
| `MASTER-INSTRUCTIONS.md` | This handbook. For me, not loaded by agents. | Me |
| `AGENTS.md` | The shared working rules, copied into every project. | Codex, Antigravity, and Claude Code via `CLAUDE.md` |
| `CLAUDE.md` | Imports `AGENTS.md` and adds Claude-only notes. | Claude Code |
| `setup.sh` | Installs or updates the skills, REA and Context7, and copies the two files into a project. | Me |
| `install.command` | Double-click in Finder to run `setup.sh` on a new Mac. | Me |
| `.env` | My Context7 API key (`CONTEXT7_API_KEY=…`). Private, git-ignored. | `setup.sh` |
| `.env.example` | Empty template for `.env`. | Me |

Project rules live in **one** file (`AGENTS.md`) so the three tools never drift apart.

## The stack

| Pack | Role | My source | Upstream |
|---|---|---|---|
| **superpowers** | Process: brainstorm → plan → TDD → verify → review → finish | [Q-alduaij/superpowers](https://github.com/Q-alduaij/superpowers) | [obra/superpowers](https://github.com/obra/superpowers) |
| **Ponytail 5** | Size: the smallest complete change; over-engineering reviews | [Q-alduaij/ponytail5](https://github.com/Q-alduaij/ponytail5) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) |
| **REA** | Reverse engineering of shipped software (binaries, apps, Electron, websites) through an MCP server | [morluto/rea](https://github.com/morluto/rea) | npm [`rea-agents`](https://www.npmjs.com/package/rea-agents), pinned to **6.7.0** |
| **Context7** | Current library and framework docs through a remote MCP server | key from [context7.com/dashboard](https://context7.com/dashboard) | [upstash/context7](https://github.com/upstash/context7) |

How they fit together:

1. **superpowers decides the process.** It says when to brainstorm, plan, test, verify and review.
2. **ponytail decides the size.** Inside each step, write the least code that fully works. It never cancels tests or verification.
3. **REA is a specialist.** Use it only when the answer depends on software you don't have the source for.

Skills included:

- superpowers: `using-superpowers`, `brainstorming`, `writing-plans`,
  `executing-plans`, `subagent-driven-development`, `test-driven-development`,
  `systematic-debugging`, `verification-before-completion`,
  `requesting-code-review`, `receiving-code-review`,
  `finishing-a-development-branch`, `using-git-worktrees`,
  `dispatching-parallel-agents`, `writing-skills`, `diagnosing-superpowers`
- ponytail: `ponytail` (levels lite / full / ultra / off), `ponytail-review`,
  `ponytail-audit`, `ponytail-debt`, `ponytail-gain`, `ponytail-help`
- REA: `reverse-engineer-anything`, plus the `rea` MCP server (about 200 tools)

## Where each tool reads things

| | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Project instructions | `CLAUDE.md` (imports `AGENTS.md`) | `AGENTS.md` | `AGENTS.md` (also `GEMINI.md`, `.agents/rules/*.md`) |
| Global instructions | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` | `~/.codex/AGENTS.md` | `~/.gemini/AGENTS.md`, `~/.gemini/config/rules/*.md` |
| Global skills | `~/.claude/skills/` | `~/.agents/skills/` | `~/.gemini/config/skills/` (app/IDE) |
| Project skills | `.claude/skills/` | `.agents/skills/` | `.agents/skills/` |
| MCP servers | `~/.claude.json` | `~/.codex/config.toml` | `~/.gemini/config/mcp_config.json` |
| Call a skill | `/ponytail-review` | `$ponytail-review` or by name | `/ponytail-review` or by name |

Skills are installed **globally**, so projects stay clean. A project only gets `AGENTS.md` and `CLAUDE.md`.

## Set up a machine

Needs `git`, `rsync`, `python3` and Node.js. REA needs Node **22.19+, 24.11+ or 26+**.

Double-click `install.command`, or run:

```bash
./setup.sh
```

You can run it again at any time. The script:

1. Clones my ponytail5 and superpowers forks and copies every skill into
   `~/.claude/skills`, `~/.agents/skills` and `~/.gemini/config/skills`. It
   backs up whatever was there to `~/.agent-kit-backups/<timestamp>/` first.
2. Runs `rea-agents@6.7.0 setup` for Claude Code, Codex and Antigravity. That
   registers the MCP server and installs the REA skill. If Node is too old, the
   script skips this step and says so.
3. Adds the remote Context7 server to all three agents, using the key in
   `.env`. It replaces any older Context7 entry, so rerunning it after
   changing the key updates every agent.

Afterwards: restart each app. In Codex, open `/hooks` and trust any hooks it lists.

### Move to another computer

1. Copy the whole `master_skills` folder, including the hidden `.env` file
   (Finder: press ⌘⇧. to show it). Use a USB drive or a private location only;
   `.env` holds my API key.
2. On the new Mac, install Node.js (`brew install node`) and the agent apps or CLIs.
3. Double-click `install.command`. If macOS blocks it, right-click → Open, or
   run `xattr -d com.apple.quarantine install.command setup.sh`.

If this folder goes into a git repo, `.gitignore` already keeps `.env` out of
it. Recreate `.env` from `.env.example` on each machine.

## Start a new project

```bash
./setup.sh ~/code/my-new-project
```

This also copies `AGENTS.md` and `CLAUDE.md` into the project. It never
overwrites files that are already there. Then:

1. Fill in the **Project** section of `AGENTS.md`: what it is, the stack, and
   the install, run, test and lint commands.
2. Commit both files.
3. Start the first session with what you want to build. superpowers'
   `brainstorming` takes it from there.

For an existing project, copy only what's missing and merge its current
instructions into the Project section by hand.

## A normal day

| I want to… | What happens |
|---|---|
| Build a feature | `brainstorming` → design → `writing-plans` → TDD per task → `requesting-code-review` → `finishing-a-development-branch` |
| Fix a bug | `systematic-debugging` → failing test → minimal fix → verify |
| Keep code small | Ponytail is on by default (full). `/ponytail ultra` to push back harder, `/ponytail lite` to relax, "stop ponytail" to turn it off. |
| Check for bloat | `/ponytail-review` (current change) or `/ponytail-audit` (whole repo) |
| See deferred shortcuts | `/ponytail-debt` lists every `shortcut:` comment |
| Learn how an app does something | Ask in plain words, e.g. "Use REA to explain how search works in this app". Only for software I'm allowed to analyze. |
| A session went wrong | "Figure out what went wrong with superpowers in this session" → `diagnosing-superpowers` |

## Update

```bash
./setup.sh
```

This rerun pulls the latest skills from my forks. To pull upstream changes into a fork first:

```bash
gh repo sync Q-alduaij/superpowers
```

```bash
gh repo sync Q-alduaij/ponytail5
```

To move REA to a newer release, change `REA_VERSION` in `setup.sh` and rerun
it. Check the [changelog](https://github.com/morluto/rea/blob/main/CHANGELOG.md)
first.

## Troubleshooting

- **REA tools don't show up.** MCP tools load only in sessions started after
  registration, so start a new one. Check with `claude mcp get rea`.
- **REA won't start, or setup says "Install Node.js…".** Node is too old. Run
  `brew upgrade node` (or install 24.11+), then rerun `./setup.sh`.
  *On this Mac today*, Homebrew Node is 24.9. The REA entries for Claude Code,
  Codex and Antigravity were set by hand to run with
  `~/.hermes/node/bin/npx` (Node 22), with that folder first on the server's
  `PATH`, so they work. Rerunning `setup.sh` after upgrading Node replaces
  them with plain `npx`, which is fine once Node is new enough.
- **`codex` command fails with `spawn … codex ENOENT`.** The CLI's native
  binary is missing. Reinstall it with `npm install -g @openai/codex`. This
  happened on 2026-10-19 and the cause is unknown. Fixed by reinstalling 0.163.0.
- **Context7 says "Invalid API key".** Create a new key at
  context7.com/dashboard, put it in `.env`, and rerun `./setup.sh`.
- **Native binary analysis fails.** REA needs Ghidra (`GHIDRA_INSTALL_DIR`),
  IDA or Hopper for native code. JavaScript, Electron and website analysis
  work without them.
- **A skill doesn't fire.** Ask for it by name, or check the skills folder for
  that tool in the table above.
- **Ponytail and superpowers seem to disagree.** Process questions go to
  superpowers, size questions to ponytail. Tests and verification are never
  skipped.

## Undo

- **Skills:** copy back from `~/.agent-kit-backups/<timestamp>/`, or delete
  the skill folders.
- **REA:** `claude mcp remove rea -s user`. Remove the `rea` entry from
  `~/.codex/config.toml` and `~/.gemini/config/mcp_config.json`. REA setup
  leaves `*.rea.backup` copies next to each config it edits.
- **Context7:** remove the `context7` entry from the same three config files.

## Trust notes

- Ponytail's upstream says to install only from `DietrichGebert/ponytail`. My
  fork is a deliberate exception. Before syncing it, check upstream changes for
  anything unexpected; it should never contain `.exe` or `.dll` files.
- REA runs third-party code from npm, pinned to one version. Read the changelog
  before bumping it.
- REA is for software I own or am allowed to analyze. Respect licenses and
  terms of service.
