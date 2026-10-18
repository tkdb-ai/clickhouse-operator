#!/usr/bin/env bash
# Run the analytic queries in sql/queries.sql with timing.
# Usage: run-queries.sh [N]   (N = 1-based query number; default: all)
source "$(dirname "$0")/lib.sh"
python3 - "$DEMO_DIR/sql/queries.sql" "${1:-all}" <<'PY' |
import sys
sql, sel = open(sys.argv[1]).read(), sys.argv[2]
parts = [p.strip() for p in sql.split(';')]
parts = [p for p in parts if any(l.strip() and not l.strip().startswith('--') for l in p.splitlines())]
for i, p in enumerate(parts, 1):
    if sel in ('all', str(i)):
        sys.stdout.write(p + '\0')
PY
while IFS= read -r -d '' q; do
  bold "$(printf '%s' "$q" | head -1)"
  printf '%s\n' "$q" | ch --time --format PrettyCompact
done
