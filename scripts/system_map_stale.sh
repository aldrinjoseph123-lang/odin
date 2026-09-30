#!/bin/sh
# Claude Code Stop hook: keeps docs/system-map.html (published as the Odin
# System Map artifact) in step with the code. When the newest commit that
# touches Odin's code, deployment or policies is newer than the newest commit
# of the map, the turn may not end until the map is updated and republished.
# Blocks once per stop (stop_hook_active), so it can never loop.
cd "$(dirname "$0")/.." || exit 0
input=$(cat)
case "$input" in *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;; esac
CODE="app.py core.py security.py db.py schema.sql constants.py policies.py scheduler.py graph.py backup.py
  send_daily_alerts.py spa.py wsgi.py routes services frontend/src Dockerfile docker-compose.yml
  docker-compose.host-tunnel.yml docker-compose.cloudflare.yml deploy"
code_at=$(git log -1 --format=%ct -- $CODE 2>/dev/null)
map_at=$(git log -1 --format=%ct -- docs/system-map.html 2>/dev/null)
[ -n "$code_at" ] || exit 0
[ -n "$map_at" ] && [ "$map_at" -ge "$code_at" ] && exit 0
since=$(git log --format='%h %s' ${map_at:+--since=@$map_at} -- $CODE | head -8 | sed 's/"/'"'"'/g' | tr '\n' ';')
cat <<JSON
{"decision": "block", "reason": "The Odin System Map is behind the code. Commits since it was last updated: ${since} Update docs/system-map.html so it stays true (flows, notifications, permissions, ways in; set fixed: \"vX.Y.Z\" on loopholes these commits closed, add any new loophole, bump MAP_STAMP), commit it, then republish it with the Artifact tool: file_path docs/system-map.html, url https://claude.ai/artifact/DLoSQZo8uDQ5B4hh3ZnnQz (read it first if this conversation has not). If nothing on the map changed, still bump MAP_STAMP.date and commit, so this check knows the map was reviewed."}
JSON
