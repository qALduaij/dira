# CLAUDE.md

@AGENTS.md

## Claude Code notes

- All project rules live in `AGENTS.md` (imported above) so every agent sees
  the same thing. Put project facts there, not here.
- Skills are in `~/.claude/skills`. Call them with the Skill tool or a slash
  command, e.g. `/ponytail ultra`, `/ponytail-review`, `/ponytail-audit`.
- REA tools come from the `rea` MCP server (`claude mcp get rea`). They appear
  only in sessions started after it was registered.
- For independent tasks that can run in parallel, use subagents
  (`dispatching-parallel-agents`, `subagent-driven-development`).
