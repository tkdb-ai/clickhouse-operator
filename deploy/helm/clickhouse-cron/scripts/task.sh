#!/bin/sh
set -eu

echo "task.sh running at $(date -Iseconds)"

# Add your periodic ClickHouse maintenance logic here, e.g.:
#   clickhouse-client --host 127.0.0.1 --user admin \
#     --password "$(cat /run/secrets/admin-password 2>/dev/null || echo "$CLICKHOUSE_ADMIN_PASSWORD")" \
#     --query "OPTIMIZE TABLE db.table FINAL"
