# ClickHouse MCP Server Setup

Enables Claude Code to query ClickHouse directly via natural language during a session.

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- A running ClickHouse instance
- A way to launch the `mcp-clickhouse` Python package — one of:
  - `mcp-clickhouse` on PATH (`pip install mcp-clickhouse` or `brew install mcp-clickhouse`)
  - [`uv`](https://docs.astral.sh/uv/) (recommended) → setup uses `uvx mcp-clickhouse`
  - [`pipx`](https://pipx.pypa.io/) → setup uses `pipx run mcp-clickhouse`
- `jq` and `curl` (for the setup script)

## Quick start

Run the interactive setup script from the repo root — it prompts for connection
details, tests the endpoint, and merges the MCP server into `~/.claude/settings.json`
without clobbering other servers:

```bash
./setup-mcp.sh
```

If you're running ClickHouse via the Helm chart in minikube, the script will
auto-suggest the minikube IP and NodePort. For non-interactive use:

```bash
CH_HOST=192.168.49.2 CH_PORT=30941 CH_USER=admin CH_PASSWORD=... \
  ./setup-mcp.sh --yes
```

## Manual configuration

Alternatively, add the following to `~/.claude/settings.json` under `mcpServers`
(adjust `command`/`args` to match how you launch `mcp-clickhouse`):

```json
{
  "mcpServers": {
    "clickhouse": {
      "command": "uvx",
      "args": ["mcp-clickhouse"],
      "env": {
        "CLICKHOUSE_HOST": "localhost",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_USER": "admin",
        "CLICKHOUSE_PASSWORD": "your-password-here",
        "CLICKHOUSE_SECURE": "false"
      }
    }
  }
}
```

If `mcp-clickhouse` is already on PATH, you can drop `args` and set `"command": "mcp-clickhouse"`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `CLICKHOUSE_PORT` | `8123` | HTTP interface port (not native TCP 9000) |
| `CLICKHOUSE_USER` | — | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | — | ClickHouse password |
| `CLICKHOUSE_SECURE` | `false` | Use HTTPS (set `true` for TLS-enabled endpoints) |

## Tools Exposed

Once connected, Claude Code has access to:

| Tool | Description |
|---|---|
| `list_databases` | List all databases |
| `list_tables` | List tables in a database with schema, row count, column info |
| `run_query` | Execute SQL (read-only by default) |

### Write access

By default queries run in read-only mode. To enable DDL/DML:

```json
"env": {
  "CLICKHOUSE_ALLOW_WRITE_ACCESS": "true"
}
```

To also allow destructive operations (`DROP`, `TRUNCATE`):

```json
"env": {
  "CLICKHOUSE_ALLOW_DROP": "true"
}
```

## Verifying the Connection

Start Claude Code — if the MCP server connects successfully you'll see `clickhouse` listed as an available integration. You can then ask Claude things like:

- "List my ClickHouse databases"
- "Show me the tables in testdb"
- "Query the trips table for the top 10 pickup neighborhoods"
