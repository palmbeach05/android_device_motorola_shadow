#!/system/bin/sh
#
# This script make a backup of pds partition to your data partition
# to allow us to use tuned battd versions without data loss risks
#
# Note: This pds partition contains unique informations related to
#       your device, like battery calibration, wifi and baseband
#

export PATH="/system/xbin:$PATH"
PDS_FILE=/data/pdsdata.img
BB_STATIC="/system/bootstrap/binary/busybox"

# Only temporary resources owned by this invocation are removed on exit.
TEMP_DIR=""
cleanup() {
	if [ -n "$TEMP_DIR" ]; then
		"$BB_STATIC" rm -f "$TEMP_DIR/image"
		"$BB_STATIC" rmdir "$TEMP_DIR"
	fi
}
trap cleanup 0
trap 'exit 1' 1 2 15

mount_pds_image() {
	mkdir -p /pds || return 1
	# A failed umount is fatal only when /pds was actually mounted.
	PDS_MOUNTED=$("$BB_STATIC" awk '$2 == "/pds" { print $2 }' /proc/mounts) || return 1
	if [ -n "$PDS_MOUNTED" ]; then
		umount /pds || return 1
	fi
	LOOP_DEV=$("$BB_STATIC" losetup -f) || return 1
	[ -n "$LOOP_DEV" ] || return 1
	"$BB_STATIC" losetup "$LOOP_DEV" "$PDS_FILE" || return 1
	if ! "$BB_STATIC" mount -o rw,nosuid,nodev,noatime,nodiratime,barrier=1 "$LOOP_DEV" /pds; then
		"$BB_STATIC" losetup -d "$LOOP_DEV"
		return 1
	fi
	echo "PDS mounted on $LOOP_DEV"
}

if [ -f /data/pds.img ]; then
	#delete old pds image that may have broken permissions
	rm -f /data/pds.img
fi

if [ ! -e "$PDS_FILE" ] && [ ! -L "$PDS_FILE" ]; then
	# sysfs reports the source partition size in 512-byte sectors.
	SOURCE_SIZE=$("$BB_STATIC" awk '
		NR == 1 && NF == 1 && $1 ~ /^[0-9]+$/ && $1 > 0 { size = $1 * 512; valid = 1 }
		END { if (NR != 1 || !valid) exit 1; printf "%.0f\n", size }
	' /sys/class/block/mmcblk1p7/size) || exit 1
	TEMP_DIR=$("$BB_STATIC" mktemp -d /data/pdsbackup.XXXXXX) || exit 1
	[ -n "$TEMP_DIR" ] || exit 1
	dd if=/dev/block/mmcblk1p7 of="$TEMP_DIR/image" bs=4096 || exit 1
	COPIED_SIZE=$("$BB_STATIC" wc -c < "$TEMP_DIR/image") || exit 1
	[ "$COPIED_SIZE" -eq "$SOURCE_SIZE" ] || exit 1
	# BusyBox mv -n preserves an image that appeared during the copy.
	"$BB_STATIC" mv -n "$TEMP_DIR/image" "$PDS_FILE" || exit 1
	[ ! -e "$TEMP_DIR/image" ] || exit 1

	#mount the fake pds
	mount_pds_image || exit 1

	#find and change moto users and groups
	"$BB_STATIC" find /pds \( -user 9000 -o -user 9003 -o -user 9004 -o -user 9007 \) -exec chown 1000 {} \;
	"$BB_STATIC" find /pds \( -group 9000 -o -group 9003 -o -group 9004 -o -group 9007 -o -group 9009 \) -exec chgrp 1000 {} \;

	echo "PDS Backed up, permissions fixed and mounted"

	if [ -d /data/battd ] ; then
		"$BB_STATIC" find /data/battd -user 9000 -exec chown 1000 {} \;
		"$BB_STATIC" find /data/battd -group 9000 -exec chgrp 1000 {} \;
	fi

else

	#mount the existing pds backup
	mount_pds_image || exit 1

	if [ -d /pds/public ] ; then
		echo "PDS partition mounted from data image."
	fi
fi
