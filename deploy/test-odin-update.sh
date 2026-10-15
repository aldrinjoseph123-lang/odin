#!/bin/sh
# Self-check for deploy/odin-update.sh, run by CI: a throw-away origin and
# server checkout, with docker/flock/sleep stubbed on PATH (failures driven by
# files in $CFG). Each scenario asserts where the server ends up.
#
#   sh deploy/test-odin-update.sh
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)
S=$(mktemp -d); trap 'rm -rf "$S"' EXIT
mkdir -p "$S/bin" "$S/home" "$S/cfg"
export PATH="$S/bin:$PATH" HOME="$S/home" ODIN_DIR="$S/app" ODIN_UPDATE_STATE="$S/state" CFG="$S/cfg"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

git init -q --bare -b main "$S/origin.git"; git clone -q "$S/origin.git" "$S/work" 2>/dev/null
( cd "$S/work" && mkdir deploy && cp "$SRC/deploy/odin-update.sh" deploy/ && echo 1.0.0 > VERSION &&
  git add -A && git commit -qm v1.0.0 && git tag v1.0.0 && git push -q origin main --tags )
git clone -q "$S/origin.git" "$S/app" 2>/dev/null; ( cd "$S/app" && git checkout -q v1.0.0 )
cp "$SRC/deploy/odin-update.sh" "$HOME/odin-update.sh"

cat > "$S/bin/docker" <<'EOF'
#!/bin/sh
tag=$(git describe --tags --exact-match HEAD 2>/dev/null || echo none)
case "$*" in
  *"ops-notices"*) cat >> "$CFG/notices";;
  *"backup.py --local"*) [ ! -e "$CFG/backup_fail" ];;
  *"up -d --build"*) ! grep -qx "$tag" "$CFG/build_fail" 2>/dev/null && rm -f "$CFG/app_down";;
  *"ps -q app"*) [ -e "$CFG/app_down" ] || echo app;;
  *"ps -q scheduler"*) echo scheduler;;
  *"inspect"*) [ -e "$CFG/app_down" ] && exit 1   # the container's name is the last word: app, scheduler
               eval "name=\${$#}"; grep -qx "$tag" "$CFG/unhealthy_$name" 2>/dev/null && echo starting || echo healthy;;
  *"preflight.py --update"*) ! grep -qx "$tag" "$CFG/preflight_fail" 2>/dev/null;;
  *"preflight.py"*) exit 1;;   # the full check would fail on settings: the updater must ask for --update
  *) true;;
esac
EOF
printf '#!/bin/sh\nexit 0\n' > "$S/bin/sleep"
printf '#!/bin/sh\nexit 0\n' > "$S/bin/flock"
chmod +x "$S/bin/"*

release() { ( cd "$S/work" && echo "${1#v}" > VERSION && git add -A && git commit -qm "$1" && git tag "$1" && git push -q origin main --tags ); }
run() { sh "$HOME/odin-update.sh" >> "$S/log" 2>&1 || true; }
on() { got=$(cd "$S/app" && git describe --tags --exact-match HEAD 2>/dev/null || echo none)
       [ "$got" = "$1" ] || { echo "FAIL $2: on $got, expected $1"; cat "$S/log"; exit 1; }; echo "ok   $2"; }

release v1.1.0; run;                                                    on v1.1.0 "a new tag deploys"
release v1.2.0; echo v1.2.0 > "$CFG/build_fail"; run;                   on v1.1.0 "a failed build rolls back"
release v1.3.0; echo v1.3.0 > "$CFG/unhealthy_app"; run;                    on v1.1.0 "an app that never turns healthy rolls back"
release v1.3.1; touch "$CFG/backup_fail"; run;                          on v1.1.0 "no backup, no update"
rm "$CFG/backup_fail"; run;                                             on v1.3.1 "the next run retries after the backup works"
release v1.4.0; printf 'v1.4.0\nv1.3.1\n' > "$CFG/build_fail"; run
touch "$CFG/app_down"; : > "$CFG/build_fail"
release v1.4.1; run;                                                    on v1.4.1 "a fixed release recovers a server left down by a failed rollback"
( cd "$S/work" && echo 'if then fi' >> deploy/odin-update.sh ); release v1.5.0; run
release v1.6.0; run;                                                    on v1.6.0 "a release whose updater does not parse cannot break the next update"
( cd "$S/work" && echo hotfix > hotfix && git add -A && git commit -qm "untagged" && git push -q origin main )
( cd "$S/app" && git fetch -q origin && git checkout -q origin/main )   # a checkout by hand, off any tag
here=$(cd "$S/app" && git rev-parse HEAD)
release v1.7.0; echo v1.7.0 > "$CFG/build_fail"; run
[ "$(cd "$S/app" && git rev-parse HEAD)" = "$here" ] || { echo "FAIL a failed update off a tag returns to that commit"; cat "$S/log"; exit 1; }; echo "ok   a failed update off a tag returns to that exact commit"

export ODIN_UPDATE_BACKOFF=1800
: > "$CFG/build_fail"; run;                                             on none "a failed tag waits before it is tried again"
export ODIN_UPDATE_BACKOFF=0; run;                                      on v1.7.0 "a failed tag is tried again after the wait"
release v1.8.0; echo v1.8.0 > "$CFG/build_fail"; run; run; run
: > "$CFG/build_fail"; run;                                             on v1.7.0 "after three failed tries the tag is left alone"
rm "$S/state/failed"; run;                                              on v1.8.0 "deleting the failed marker tries it again"
release v1.9.0; touch "$S/state/hold"; run;                             on v1.8.0 "a hold pauses updates"
rm "$S/state/hold"; run;                                                on v1.9.0 "removing the hold resumes them"
: > "$CFG/notices"; release v1.10.0; echo v1.10.0 > "$CFG/unhealthy_scheduler"; run
on v1.9.0 "a scheduler that never turns healthy rolls back"
grep -q "update to Odin v1.10.0 failed and the server went back to v1.9.0" "$CFG/notices" || { echo "FAIL the admins get a notice"; cat "$S/log"; exit 1; }; echo "ok   a failed update leaves a notice for the admins"
release v1.10.1; echo v1.10.1 > "$CFG/preflight_fail"; run;             on v1.9.0 "a failed preflight rolls back"
