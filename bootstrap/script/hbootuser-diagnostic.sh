#!/system/bootstrap/binary/busybox ash
# Opt-in stock-kernel startup probe. Never pass a descriptor to the candidate.
BB_STATIC=/system/bootstrap/binary/busybox
MARKER=/cache/recovery/hbootuser-diagnostic.once
CANDIDATE=/system/bootstrap/binary/hbootuser-test
LOG=/cache/recovery/hbootuser-diagnostic.log

[ -f "$MARKER" ] && [ ! -L "$MARKER" ] || exit 0
[ -f "$CANDIDATE" ] && [ -x "$CANDIDATE" ] && [ ! -L "$CANDIDATE" ] || exit 0

# /cache must be a real, writable mount, not a directory on the rootfs.
mounted=no
while read device mountpoint filesystem options rest; do
    [ "$mountpoint" = /cache ] || continue
    case ",$options," in *,rw,*) mounted=yes ;; esac
done < /proc/mounts
[ "$mounted" = yes ] || exit 0

# Check this BusyBox at runtime; in particular, do not assume timeout exists.
APPLETS=$($BB_STATIC --list) || exit 0
for required in ash cat chmod mkdir rm sleep sync uname; do
    case "
$APPLETS
" in *"
$required
"*) ;; *) exit 0 ;; esac
done
$BB_STATIC ash -c 'ulimit -f 32 && kill -0 $$' || exit 0
$BB_STATIC sleep 0 || exit 0

# An atomic directory also prevents concurrent logwrapper invocations.
WORK=/cache/recovery/hbootuser-diagnostic.work
$BB_STATIC mkdir "$WORK" 2>/dev/null || exit 0
cleanup() {
    $BB_STATIC rm -rf "$WORK"
}
trap cleanup EXIT
$BB_STATIC chmod 700 "$WORK" || exit 0
[ ! -L "$LOG" ] || exit 0
# Test actual writes, including the bounded candidate output file, before arming.
(umask 077; : > "$WORK/output") || exit 0
exec 3> "$LOG" || exit 0
$BB_STATIC chmod 600 "$LOG" || exit 0
{
    echo 'hbootuser startup diagnostic: no arguments; no module or handoff.'
    echo 'Usage output and exit status 1 are expected.'
    echo 'Candidate output limit: 32 shell file-size blocks; watchdog: 10 seconds.'
    $BB_STATIC uname -a
    echo 'Alignment settings:'
    if [ -r /proc/cpu/alignment ]; then
        $BB_STATIC cat /proc/cpu/alignment
    else
        echo 'unavailable'
    fi
} >&3 || exit 0
$BB_STATIC sync || exit 0

# Hold the runner until the watchdog is armed and the marker is consumed.
(
    ulimit -f 32 || exit 125
    while [ ! -f "$WORK/go" ]; do
        $BB_STATIC sleep 1 || exit 125
    done
    exec "$CANDIDATE"
) > "$WORK/output" 2>&1 &
runner=$!
(
    : > "$WORK/ready" || exit 1
    $BB_STATIC sleep 10 || { kill -KILL "$runner"; exit 1; }
    echo timeout > "$WORK/timeout"
    kill -KILL "$runner" 2>/dev/null
) &
watchdog=$!
abort() {
    kill -KILL "$runner" "$watchdog" 2>/dev/null
    wait "$runner" 2>/dev/null
    wait "$watchdog" 2>/dev/null
    exit 0
}
tries=0
while [ ! -f "$WORK/ready" ]; do
    tries=$((tries + 1))
    [ "$tries" -le 3 ] || abort
    kill -0 "$watchdog" 2>/dev/null || abort
    $BB_STATIC sleep 1 || abort
done
kill -0 "$watchdog" 2>/dev/null || abort
kill -0 "$runner" 2>/dev/null || abort
$BB_STATIC rm "$MARKER" || abort
[ ! -e "$MARKER" ] || abort
$BB_STATIC sync || abort
: > "$WORK/go" || abort
wait "$runner"
status=$?
kill -KILL "$watchdog" 2>/dev/null
wait "$watchdog" 2>/dev/null
{
    $BB_STATIC cat "$WORK/output"
    echo
    echo "Exit status: $status"
    if [ -f "$WORK/timeout" ]; then
        echo 'Watchdog expired (includes runner startup delay).'
    fi
} >&3
exec 3>&-
$BB_STATIC sync
exit 0
