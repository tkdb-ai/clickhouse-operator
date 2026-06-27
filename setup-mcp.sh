#!/usr/bin/env bash
# Interactive setup for the ClickHouse MCP server in Claude Code.
#
# Registers the ClickHouse MCP server in ~/.claude/settings.json so Claude Code
# can list databases, list tables, and run SQL against your ClickHouse instance.
#
# Usage:
#   ./setup-mcp.sh                # interactive
#   CH_HOST=... CH_PORT=... CH_USER=... CH_PASSWORD=... ./setup-mcp.sh --yes
#
# Env overrides (skip the matching prompt when set):
#   CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_ALLOW_WRITE (true|false)

set -euo pipefail

SETTINGS_FILE="${HOME}/.claude/settings.json"
SERVER_NAME="clickhouse"
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0 ;;
  esac
done

err() { printf 'error: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

# --- prereqs --------------------------------------------------------------
command -v jq >/dev/null || err "jq is required (install with your package manager)"
command -v curl >/dev/null || err "curl is required"

if ! command -v npx >/dev/null; then
  err "npx not found — install Node.js (https://nodejs.org) or set up @clickhouse/mcp-server manually"
fi

if ! command -v claude >/dev/null; then
  printf 'warning: claude CLI not found on PATH — settings will still be written, but make sure Claude Code is installed.\n' >&2
fi

mkdir -p "$(dirname "$SETTINGS_FILE")"

# --- detect a minikube NodePort if a helm release exposes one -------------
suggest_host=""
suggest_port=""
if command -v kubectl >/dev/null && command -v minikube >/dev/null; then
  if minikube status >/dev/null 2>&1; then
    suggest_host="$(minikube ip 2>/dev/null || true)"
    suggest_port="$(kubectl get svc -A -o json 2>/dev/null \
      | jq -r '.items[] | select(.spec.type=="NodePort") | .spec.ports[]? | select(.port==8123 or .name=="http") | .nodePort' \
      | head -n1)"
  fi
fi
: "${suggest_host:=localhost}"
: "${suggest_port:=8123}"

# --- prompts (or env) -----------------------------------------------------
prompt() {
  # prompt VAR_NAME "label" "default"  -> sets the named variable
  local var=$1 label=$2 default=$3 reply
  if [ -n "${!var:-}" ]; then return; fi
  if [ "$ASSUME_YES" -eq 1 ]; then printf -v "$var" '%s' "$default"; return; fi
  if [ -n "$default" ]; then
    read -r -p "$label [$default]: " reply
    printf -v "$var" '%s' "${reply:-$default}"
  else
    read -r -p "$label: " reply
    printf -v "$var" '%s' "$reply"
  fi
}

prompt_secret() {
  local var=$1 label=$2 reply
  if [ -n "${!var:-}" ]; then return; fi
  if [ "$ASSUME_YES" -eq 1 ]; then printf -v "$var" '%s' ""; return; fi
  read -r -s -p "$label: " reply; echo
  printf -v "$var" '%s' "$reply"
}

info "Configuring ClickHouse MCP server for Claude Code"
prompt CH_HOST "ClickHouse host" "$suggest_host"
prompt CH_PORT "ClickHouse HTTP port" "$suggest_port"
prompt CH_USER "ClickHouse user" "default"
prompt_secret CH_PASSWORD "ClickHouse password (input hidden)"
prompt CH_ALLOW_WRITE "Allow write access (true/false)" "false"

case "$CH_ALLOW_WRITE" in
  true|false) ;;
  *) err "CH_ALLOW_WRITE must be 'true' or 'false' (got: $CH_ALLOW_WRITE)" ;;
esac

# --- test connection ------------------------------------------------------
info "Testing connection to http://${CH_HOST}:${CH_PORT}/ping"
if ! curl -fsS --max-time 5 \
     -u "${CH_USER}:${CH_PASSWORD}" \
     "http://${CH_HOST}:${CH_PORT}/ping" >/dev/null; then
  printf 'warning: could not reach ClickHouse at http://%s:%s — settings will still be written. Fix connectivity before restarting Claude Code.\n' \
    "$CH_HOST" "$CH_PORT" >&2
else
  info "ClickHouse responded OK"
fi

# --- merge into settings.json --------------------------------------------
new_server=$(jq -n \
  --arg cmd "npx" \
  --arg pkg "@clickhouse/mcp-server" \
  --arg host "$CH_HOST" \
  --arg port "$CH_PORT" \
  --arg user "$CH_USER" \
  --arg pass "$CH_PASSWORD" \
  --arg write "$CH_ALLOW_WRITE" \
  '{
     command: $cmd,
     args: ["-y", $pkg],
     env: {
       CLICKHOUSE_HOST: $host,
       CLICKHOUSE_PORT: $port,
       CLICKHOUSE_USERNAME: $user,
       CLICKHOUSE_PASSWORD: $pass,
       CLICKHOUSE_ALLOW_WRITE_ACCESS: $write
     }
   }')

if [ -f "$SETTINGS_FILE" ]; then
  backup="${SETTINGS_FILE}.bak.$(date +%s)"
  cp "$SETTINGS_FILE" "$backup"
  info "Backed up existing settings to $backup"
  tmp=$(mktemp)
  jq --argjson srv "$new_server" --arg name "$SERVER_NAME" \
     '.mcpServers = ((.mcpServers // {}) | .[$name] = $srv)' \
     "$SETTINGS_FILE" > "$tmp"
  mv "$tmp" "$SETTINGS_FILE"
else
  jq -n --argjson srv "$new_server" --arg name "$SERVER_NAME" \
     '{mcpServers: {($name): $srv}}' > "$SETTINGS_FILE"
fi

chmod 600 "$SETTINGS_FILE"

info "Wrote MCP server '$SERVER_NAME' to $SETTINGS_FILE"
info "Restart Claude Code, then try: \"list my ClickHouse databases\""
