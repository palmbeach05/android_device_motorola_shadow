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

$BB_STATIC mkdir -p "$BOOT_DIR" || fail "Cannot create $BOOT_DIR"
$BB_STATIC cp -f /system/bootstrap/2nd-boot/* "$BOOT_DIR/" || fail "Cannot stage boot files"
$BB_STATIC cp -f /system/bootstrap/binary/hbootuser "$BOOT_DIR/hbootuser" || fail "Cannot stage hbootuser"
$BB_STATIC cp -f /system/bootstrap/modules/hbootmod.ko "$BOOT_DIR/hbootmod.ko" || fail "Cannot stage hbootmod"
$BB_STATIC chmod 755 "$BOOT_DIR/"* || fail "Cannot set boot file permissions"

$BB_STATIC sync || fail "Cannot sync staged files"
cd "$BOOT_DIR" || fail "Cannot enter $BOOT_DIR"

$BB_STATIC umount /acct
$BB_STATIC umount /dev/cpuctl
$BB_STATIC umount /dev/pts
$BB_STATIC umount /mnt/asec
$BB_STATIC umount /mnt/obb
$BB_STATIC umount /cache
$BB_STATIC umount /data

$BB_STATIC echo 18 > /sys/class/leds/lcd-backlight/brightness

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
