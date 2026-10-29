#!/sbin/sh
# 2nd-boot.sh

BB_STATIC="/system/bootstrap/binary/busybox"
BOOT_DIR="/2ndboot"

$BB_STATIC mount -o remount,rw rootfs /
$BB_STATIC mount -o remount,rw /system
$BB_STATIC mount -o remount,rw /

$BB_STATIC mkdir -p /pds
$BB_STATIC mount -t ext3 /dev/block/mmcblk1p7 /pds 2>/dev/null

fail()
{
    echo "2nd-boot: $*" >&2
    exit 1
}

$BB_STATIC mkdir -p $BOOT_DIR || fail "Cannot create $BOOT_DIR"
$BB_STATIC cp -f /system/bootstrap/2nd-boot/* $BOOT_DIR/ || fail "Cannot stage boot files"
$BB_STATIC cp -f /system/bootstrap/binary/hbootuser $BOOT_DIR/hbootuser || fail "Cannot stage hbootuser"
$BB_STATIC cp -f /system/bootstrap/modules/hbootmod.ko $BOOT_DIR/hbootmod.ko || fail "Cannot stage hbootmod"
$BB_STATIC chmod 755 $BOOT_DIR/* || fail "Cannot set boot file permissions"

# --- Preserve stock hboot command-line parameters ---
# Read the authoritative values from the running system's /proc/cmdline
# (do NOT use ro.serialno / ro.boot.serialno / ro.ril.barcode / /pds, they
# can be absent or hold stale/incorrect values) and forward only the
# allowlisted stock tokens to both the normal and recovery hboot command
# lines: androidboot.serialno, the final androidboot.bootloader (the stock
# cmdline may list it more than once, e.g. androidboot.bootloader=0x0000
# followed by androidboot.bootloader=3004; only the last one is authoritative),
# and brdrev.
echo "2nd-boot: reading stock command line"
LC_ALL=C $BB_STATIC awk '
    NR != 1 || $0 !~ /^[ -~]+$/ || $0 !~ /[^ ]/ { bad = 1 }
    END { if (bad || NR != 1) exit 1 }
' /proc/cmdline || fail "Invalid stock command line"
STOCK_CMDLINE=`$BB_STATIC cat /proc/cmdline` || fail "Cannot read /proc/cmdline"
[ -n "$STOCK_CMDLINE" ] || fail "Empty /proc/cmdline"

is_valid_token() {
    $BB_STATIC echo "$1" | $BB_STATIC grep -Eq '^[A-Za-z0-9._-]+$'
}

SERIAL=`$BB_STATIC echo "$STOCK_CMDLINE" | $BB_STATIC grep -o 'androidboot\.serialno=[^ ]*' | $BB_STATIC tail -n1 | $BB_STATIC sed 's/^androidboot\.serialno=//'`
BOOTLOADER=`$BB_STATIC echo "$STOCK_CMDLINE" | $BB_STATIC grep -o 'androidboot\.bootloader=[^ ]*' | $BB_STATIC tail -n1 | $BB_STATIC sed 's/^androidboot\.bootloader=//'`
BRDREV=`$BB_STATIC echo "$STOCK_CMDLINE" | $BB_STATIC grep -o 'brdrev=[^ ]*' | $BB_STATIC tail -n1 | $BB_STATIC sed 's/^brdrev=//'`

PAYLOAD=""

if [ -n "$SERIAL" ] && is_valid_token "$SERIAL"; then
    PAYLOAD="$PAYLOAD androidboot.serialno=$SERIAL"
else
    $BB_STATIC echo "2nd-boot: missing or invalid androidboot.serialno in /proc/cmdline, skipping"
fi

if [ -n "$BOOTLOADER" ] && is_valid_token "$BOOTLOADER"; then
    PAYLOAD="$PAYLOAD androidboot.bootloader=$BOOTLOADER"
else
    $BB_STATIC echo "2nd-boot: missing or invalid androidboot.bootloader in /proc/cmdline, skipping"
fi

if [ -n "$BRDREV" ] && is_valid_token "$BRDREV"; then
    PAYLOAD="$PAYLOAD brdrev=$BRDREV"
else
    $BB_STATIC echo "2nd-boot: missing or invalid brdrev in /proc/cmdline, skipping"
fi

# Validate both baselines even when no stock tokens can be forwarded.
for CMDFILE in "$BOOT_DIR/cmdline" "$BOOT_DIR/cmdline-recovery"; do
    [ -f "$CMDFILE" ] && [ -r "$CMDFILE" ] || fail "Cannot read $CMDFILE"
    LC_ALL=C $BB_STATIC awk '
        NR != 1 || length($0) > 1023 || $0 !~ /^[ -~]+$/ || $0 !~ /[^ ]/ { bad = 1 }
        END { if (bad || NR != 1) exit 1 }
    ' "$CMDFILE" || fail "Invalid command-line baseline: $CMDFILE"
    BASELINE=`$BB_STATIC cat "$CMDFILE"` || fail "Cannot read $CMDFILE"
    if [ -n "$PAYLOAD" ]; then
        NEWLINE="$BASELINE$PAYLOAD"
        LEN=`$BB_STATIC printf '%s' "$NEWLINE" | $BB_STATIC wc -c` ||
            fail "Cannot measure command line: $CMDFILE"
        [ "$LEN" -le 1023 ] || fail "Stock payload too long for $CMDFILE"
        TMPFILE="$CMDFILE.tmp"
        if ! $BB_STATIC printf '%s\n' "$NEWLINE" > "$TMPFILE"; then
            $BB_STATIC rm -f "$TMPFILE"
            fail "Cannot write command line: $CMDFILE"
        fi
        if ! $BB_STATIC mv -f "$TMPFILE" "$CMDFILE"; then
            $BB_STATIC rm -f "$TMPFILE"
            fail "Cannot replace command line: $CMDFILE"
        fi
    fi
done

echo "2nd-boot: preparation complete; unmounting filesystems"

$BB_STATIC sync

$BB_STATIC umount /acct
$BB_STATIC umount /dev/cpuctl
$BB_STATIC umount /dev/pts
$BB_STATIC umount /mnt/asec
$BB_STATIC umount /mnt/obb
$BB_STATIC umount /cache
$BB_STATIC umount /data

$BB_STATIC echo 18 > /sys/class/leds/lcd-backlight/brightness

cd "$BOOT_DIR" || fail "Cannot enter $BOOT_DIR"

$BB_STATIC echo "Inserting hbootmod..."
if [ "$1" = "uart" ]; then
    $BB_STATIC insmod ./hbootmod.ko kill_dss=1 emu_uart=115200 || fail "Cannot load hbootmod (UART)"
else
    $BB_STATIC insmod ./hbootmod.ko kill_dss=1 || fail "Cannot load hbootmod"
fi

# Accept exactly one character-device registration, not a substring match.
MAJOR=$($BB_STATIC awk '
    $0 == "Character devices:" { chars = 1; next }
    $0 == "Block devices:" { chars = 0 }
    chars && NF == 2 && $2 == "hbootctrl" {
        major = $1
        count++
    }
    END {
        if (count == 1 && major ~ /^[0-9]+$/ && major > 0)
            print major
        else
            exit 1
    }
' /proc/devices) || fail "Cannot find a unique hbootctrl character-device major"

# Remove any stale node and create the replacement with owner-only access.
umask 077
$BB_STATIC rm -f /dev/hbootctrl || fail "Cannot remove stale hbootctrl device"
$BB_STATIC mknod /dev/hbootctrl c "$MAJOR" 0 || fail "Cannot create hbootctrl device"
$BB_STATIC chmod 600 /dev/hbootctrl || fail "Cannot restrict hbootctrl permissions"
[ -c /dev/hbootctrl ] || fail "hbootctrl is not a character device"

$BB_STATIC echo "Jumping to custom kernel..."
if [ "$1" = "recovery" ]; then
    ./hbootuser ./hboot_recovery.cfg || fail "Recovery boot failed"
else
    ./hbootuser ./hboot.cfg || fail "System boot failed"
fi
