#!/usr/bin/env bash
# Run in a second terminal during the demo steps. Fires a distributed query every
# second through the Service and prints OK/FAIL, so the audience can see the
# cluster stays up while pods are added, reconfigured, upgraded or killed.
source "$(dirname "$0")/lib.sh"
ok=0; fail=0
while true; do
  if out=$(ch --connect_timeout 2 --receive_timeout 5 -q \
      "SELECT hostName(), version(), count() FROM demo.trips FORMAT TSV" 2>&1); then
    ok=$((ok + 1))
    read -r host ver rows <<<"$out"
    printf '\033[0;32m%s OK   \033[0m served-by=%-28s ver=%-12s rows=%s  (ok=%d fail=%d)\n' \
      "$(date +%T)" "$host" "$ver" "$rows" "$ok" "$fail"
  else
    fail=$((fail + 1))
    printf '\033[0;31m%s FAIL \033[0m %s  (ok=%d fail=%d)\n' "$(date +%T)" "$(echo "$out" | head -1 | cut -c1-80)" "$ok" "$fail"
  fi
  sleep 1
done
