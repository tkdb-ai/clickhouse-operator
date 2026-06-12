# ClickHouse MCP Server Setup

Enables Claude Code to query ClickHouse directly via natural language during a session.

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Node.js / npx available
- A running ClickHouse instance

## Configuration

Add the following to `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "clickhouse": {
      "command": "npx",
      "args": ["-y", "@clickhouse/mcp-server"],
      "env": {
        "CLICKHOUSE_HOST": "localhost",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_USERNAME": "admin",
        "CLICKHOUSE_PASSWORD": "your-password-here"
      }
    }
  }
}
```

The `npx -y` flag downloads and runs `@clickhouse/mcp-server` automatically — no separate install step needed.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `CLICKHOUSE_PORT` | `8123` | HTTP interface port (not native TCP 9000) |
| `CLICKHOUSE_USERNAME` | — | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | — | ClickHouse password |

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
