#!/sbin/sh
# 2nd-boot.sh

BB_STATIC="/system/bootstrap/binary/busybox"
BOOT_DIR="/2ndboot"

$BB_STATIC mount -o remount,rw rootfs /
$BB_STATIC mount -o remount,rw /system
$BB_STATIC mount -o remount,rw /

$BB_STATIC mkdir -p /pds
$BB_STATIC mount -t ext3 /dev/block/mmcblk1p7 /pds 2>/dev/null

$BB_STATIC mkdir -p $BOOT_DIR
$BB_STATIC cp -f /system/bootstrap/2nd-boot/* $BOOT_DIR/
$BB_STATIC mkdir -p $BOOT_DIR
$BB_STATIC cp -f /system/bootstrap/2nd-boot/* $BOOT_DIR/
$BB_STATIC cp -f /system/bootstrap/binary/hbootuser $BOOT_DIR/hbootuser
$BB_STATIC cp -f /system/bootstrap/modules/hbootmod.ko $BOOT_DIR/hbootmod.ko
$BB_STATIC chmod 755 $BOOT_DIR/*

# --- Preserve stock HBoot serial number ---
# Read the authoritative serial from the running system's /proc/cmdline
# (do NOT use ro.serialno / ro.boot.serialno / ro.ril.barcode, they can be
# absent or hold the modem barcode instead of the stock HBoot serial) and
# forward it to both the normal and recovery hboot command lines.
SERIAL=`$BB_STATIC cat /proc/cmdline | $BB_STATIC grep -o 'androidboot\.serialno=[^ ]*' | $BB_STATIC sed 's/^androidboot\.serialno=//'`

if [ -n "$SERIAL" ] && $BB_STATIC echo "$SERIAL" | $BB_STATIC grep -Eq '^[A-Za-z0-9._-]+$'; then
    for CMDFILE in $BOOT_DIR/cmdline $BOOT_DIR/cmdline-recovery; do
        BASELINE=`$BB_STATIC cat $CMDFILE`
        NEWLINE="$BASELINE androidboot.serialno=$SERIAL"
        LEN=`$BB_STATIC echo -n "$NEWLINE" | $BB_STATIC wc -c`
        if [ "$LEN" -le 1023 ]; then
            $BB_STATIC echo "$NEWLINE" > $CMDFILE
        else
            $BB_STATIC echo "2nd-boot: serial payload too long for $CMDFILE, skipping serial injection"
        fi
    done
else
    $BB_STATIC echo "2nd-boot: no valid androidboot.serialno found in /proc/cmdline, skipping serial injection"
fi

$BB_STATIC sync

$BB_STATIC umount /acct
$BB_STATIC umount /dev/cpuctl
$BB_STATIC umount /dev/pts
$BB_STATIC umount /mnt/asec
$BB_STATIC umount /mnt/obb
$BB_STATIC umount /cache
$BB_STATIC umount /data

$BB_STATIC echo 18 > /sys/class/leds/lcd-backlight/brightness

cd $BOOT_DIR

$BB_STATIC echo "Inserting hbootmod..."
if [ "$1" = "uart" ]; then
    $BB_STATIC insmod ./hbootmod.ko kill_dss=1 emu_uart=115200
else
    $BB_STATIC insmod ./hbootmod.ko kill_dss=1
fi

MAJOR=`$BB_STATIC cat /proc/devices | $BB_STATIC grep hboot | $BB_STATIC awk '{print $1}'`
$BB_STATIC mknod /dev/hbootctrl c $MAJOR 0

$BB_STATIC echo "Jumping to custom kernel..."
if [ "$1" = "recovery" ]; then
    ./hbootuser ./hboot_recovery.cfg
else
    ./hbootuser ./hboot.cfg
fi
