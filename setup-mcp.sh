#!/usr/bin/env bash
# Interactive setup for the ClickHouse MCP server in Claude Code.
#
# Registers the ClickHouse MCP server in ~/.claude/settings.json so Claude Code
# can list databases, list tables, and run SQL against your ClickHouse instance.
#
# The runtime is the official Python package `mcp-clickhouse`. The script auto-
# picks the first available launcher in this order:
#   1. an existing `mcp-clickhouse` binary on PATH (e.g. installed via brew/pip)
#   2. `uvx mcp-clickhouse` (recommended — uv handles install + isolation)
#   3. `pipx run mcp-clickhouse`
# If none is found, the script tells you which to install and exits.
#
# Usage:
#   ./setup-mcp.sh                # interactive
#   CH_HOST=... CH_PORT=... CH_USER=... CH_PASSWORD=... ./setup-mcp.sh --yes
#
# Env overrides (skip the matching prompt when set):
#   CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_ALLOW_WRITE (true|false)
#   HELM_RELEASE (kubectl namespace lookup — defaults to "chi")

set -euo pipefail

SETTINGS_FILE="${HOME}/.claude/settings.json"
SERVER_NAME="clickhouse"
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0 ;;
  esac
done

err() { printf 'error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'warning: %s\n' "$*" >&2; }
info() { printf '==> %s\n' "$*"; }

# --- prereqs --------------------------------------------------------------
command -v jq >/dev/null || err "jq is required (install with your package manager)"
command -v curl >/dev/null || err "curl is required"

# Pick an MCP launcher.
MCP_CMD=""
MCP_ARGS_JSON="[]"
if command -v mcp-clickhouse >/dev/null; then
  MCP_CMD="$(command -v mcp-clickhouse)"
elif command -v uvx >/dev/null; then
  MCP_CMD="$(command -v uvx)"
  MCP_ARGS_JSON='["mcp-clickhouse"]'
elif command -v pipx >/dev/null; then
  MCP_CMD="$(command -v pipx)"
  MCP_ARGS_JSON='["run", "mcp-clickhouse"]'
else
  err "no MCP launcher found. Install one of:
    - mcp-clickhouse  (pip install mcp-clickhouse, or brew install mcp-clickhouse)
    - uv              (https://docs.astral.sh/uv/) — then uvx will be available
    - pipx            (https://pipx.pypa.io/)"
fi
info "Using MCP launcher: $MCP_CMD $(echo "$MCP_ARGS_JSON" | jq -r 'join(" ")')"

if ! command -v claude >/dev/null; then
  warn "claude CLI not found on PATH — settings will still be written, but make sure Claude Code is installed."
fi

mkdir -p "$(dirname "$SETTINGS_FILE")"

# --- detect a minikube NodePort and the helm-created admin secret ---------
suggest_host=""
suggest_port=""
suggest_password=""
HELM_RELEASE="${HELM_RELEASE:-chi}"

if command -v kubectl >/dev/null && command -v minikube >/dev/null && minikube status >/dev/null 2>&1; then
  suggest_host="$(minikube ip 2>/dev/null || true)"
  suggest_port="$(kubectl get svc -A -o json 2>/dev/null \
    | jq -r '.items[] | select(.spec.type=="NodePort") | .spec.ports[]? | select(.port==8123 or .name=="http") | .nodePort' \
    | head -n1)"
  # Helm chart stores admin password in a secret named "<release>-admin" with key "admin"
  suggest_password="$(kubectl get secret -A -o json 2>/dev/null \
    | jq -r --arg r "$HELM_RELEASE" '.items[] | select(.metadata.name | endswith("-admin")) | select(.metadata.name | startswith($r)) | .data.admin' \
    | head -n1 | { read -r b64 || true; [ -n "${b64:-}" ] && echo "$b64" | base64 -d || true; })"
fi
: "${suggest_host:=localhost}"
: "${suggest_port:=8123}"

# --- prompts (or env) -----------------------------------------------------
prompt() {
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
  local var=$1 label=$2 default=$3 reply
  if [ -n "${!var:-}" ]; then return; fi
  if [ "$ASSUME_YES" -eq 1 ]; then printf -v "$var" '%s' "$default"; return; fi
  if [ -n "$default" ]; then
    read -r -s -p "$label [press enter to use detected]: " reply; echo
    printf -v "$var" '%s' "${reply:-$default}"
  else
    read -r -s -p "$label: " reply; echo
    printf -v "$var" '%s' "$reply"
  fi
}

info "Configuring ClickHouse MCP server for Claude Code"
prompt CH_HOST "ClickHouse host" "$suggest_host"
prompt CH_PORT "ClickHouse HTTP port" "$suggest_port"
prompt CH_USER "ClickHouse user" "admin"
prompt_secret CH_PASSWORD "ClickHouse password (hidden)" "$suggest_password"
prompt CH_ALLOW_WRITE "Allow write access (true/false)" "false"

case "$CH_ALLOW_WRITE" in
  true|false) ;;
  *) err "CH_ALLOW_WRITE must be 'true' or 'false' (got: $CH_ALLOW_WRITE)" ;;
esac

# --- test connection ------------------------------------------------------
info "Testing connection to http://${CH_HOST}:${CH_PORT}/ping"
if ! curl -fsS --max-time 5 -u "${CH_USER}:${CH_PASSWORD}" \
     "http://${CH_HOST}:${CH_PORT}/ping" >/dev/null; then
  warn "could not reach ClickHouse at http://${CH_HOST}:${CH_PORT} — settings will still be written. Fix connectivity before restarting Claude Code."
else
  info "ClickHouse responded OK"
fi

# --- merge into settings.json --------------------------------------------
# Note: the mcp-clickhouse package uses CLICKHOUSE_USER (not USERNAME).
new_server=$(jq -n \
  --arg cmd "$MCP_CMD" \
  --argjson args "$MCP_ARGS_JSON" \
  --arg host "$CH_HOST" \
  --arg port "$CH_PORT" \
  --arg user "$CH_USER" \
  --arg pass "$CH_PASSWORD" \
  --arg write "$CH_ALLOW_WRITE" \
  '{
     command: $cmd,
     args: $args,
     env: {
       CLICKHOUSE_HOST: $host,
       CLICKHOUSE_PORT: $port,
       CLICKHOUSE_USER: $user,
       CLICKHOUSE_PASSWORD: $pass,
       CLICKHOUSE_SECURE: "false",
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
