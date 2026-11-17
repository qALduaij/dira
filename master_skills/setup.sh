#!/usr/bin/env bash
# Install or update the agent kit for Claude Code, Codex and Antigravity.
#   ./setup.sh             skills (ponytail5 + superpowers) and REA, globally
#   ./setup.sh <project>   same, then copy AGENTS.md and CLAUDE.md into <project>
set -euo pipefail

KIT=$(cd "$(dirname "$0")" && pwd)
REA_VERSION=6.7.0
REPOS=(https://github.com/Q-alduaij/ponytail5.git https://github.com/Q-alduaij/superpowers.git)
DESTS=("$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.gemini/config/skills")
BACKUP="$HOME/.agent-kit-backups/$(date +%Y%m%d-%H%M%S)"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for url in "${REPOS[@]}"; do
  src="$tmp/$(basename "$url" .git)"
  git clone -q --depth 1 "$url" "$src"
  for skill in "$src"/skills/*/; do
    name=$(basename "$skill")
    for dest in "${DESTS[@]}"; do
      if [ -d "$dest/$name" ]; then
        mkdir -p "$BACKUP/${dest#"$HOME"/}"
        cp -Rp "$dest/$name" "$BACKUP/${dest#"$HOME"/}/"
      fi
      mkdir -p "$dest/$name"
      rsync -a --delete "$skill" "$dest/$name/"
    done
  done
  echo "✓ skills from $url"
done
[ -d "$BACKUP" ] && echo "  previous copies backed up to $BACKUP"

# REA requires Node 22.19+, 24.11+ or 26+.
if node -e 'const [a,b]=process.versions.node.split(".").map(Number);
            process.exit((a==22&&b>=19)||(a==24&&b>=11)||a>=26?0:1)' 2>/dev/null; then
  npx -y "rea-agents@$REA_VERSION" setup --yes \
    --client claude_code --client codex --client antigravity
  echo "✓ REA $REA_VERSION registered"
else
  echo "✗ skipped REA: Node $(node -v 2>/dev/null || echo missing) is too old."
  echo "  Install Node 22.19+, 24.11+ or 26+ (brew upgrade node), then rerun."
fi

# Context7 docs server (remote), using CONTEXT7_API_KEY from .env next to this script or the environment.
if [ -f "$KIT/.env" ]; then set -a; . "$KIT/.env"; set +a; fi
if [ -n "${CONTEXT7_API_KEY:-}" ]; then
  python3 - "$CONTEXT7_API_KEY" <<'EOF'
import json, os, re, sys
key, url = sys.argv[1], "https://mcp.context7.com/mcp"
home = os.path.expanduser("~")

def save(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f: f.write(text)
    os.replace(path + ".tmp", path)

def set_json(path, outer, entry):
    data = json.load(open(path)) if os.path.exists(path) else {}
    data.setdefault(outer, {})["context7"] = entry
    save(path, json.dumps(data, indent=2) + "\n")

set_json(f"{home}/.claude.json", "mcpServers",
         {"type": "http", "url": url, "headers": {"CONTEXT7_API_KEY": key}})
set_json(f"{home}/.gemini/config/mcp_config.json", "mcpServers",
         {"serverUrl": url, "headers": {"Authorization": f"Bearer {key}"}})

toml = f"{home}/.codex/config.toml"
text = open(toml).read() if os.path.exists(toml) else ""
section = (f'[mcp_servers.context7]\nurl = "{url}"\n'
           f'http_headers = {{ "Authorization" = "Bearer {key}" }}\n\n')
text, found = re.subn(r"(?ms)^\[mcp_servers\.context7\]\n.*?(?=^\[|\Z)", lambda m: section, text)
save(toml, text if found else text.rstrip("\n") + "\n\n" + section)
EOF
  echo "✓ Context7 configured with your API key"
else
  echo "✗ skipped Context7: put CONTEXT7_API_KEY=... in $KIT/.env"
fi

if [ $# -gt 0 ]; then
  mkdir -p "$1"
  for f in AGENTS.md CLAUDE.md; do
    if [ -e "$1/$f" ]; then echo "• kept existing $1/$f"
    else cp "$KIT/$f" "$1/$f" && echo "✓ added $1/$f"; fi
  done
  echo "  Next: fill in the Project section of $1/AGENTS.md"
fi

echo "Restart Claude Code, Codex and Antigravity to load the changes."
