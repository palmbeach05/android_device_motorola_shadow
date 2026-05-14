#!/system/bin/sh
#
# This script make a backup of pds partition to your data partition
# to allow us to use tuned battd versions without data loss risks
#
# Note: This pds partition contains unique informations related to
#       your device, like battery calibration, wifi and baseband
#

export PATH=/system/xbin:$PATH
PDS_FILE=/data/pdsdata.img
BB_STATIC="/system/bootstrap/binary/busybox"

mount_pds_image() {
	mkdir -p /pds
	umount /pds 2>/dev/null
	LOOP_DEV=$($BB_STATIC losetup -f)
	$BB_STATIC losetup $LOOP_DEV $PDS_FILE
	$BB_STATIC mount -o rw,nosuid,nodev,noatime,nodiratime,barrier=1 $LOOP_DEV /pds
	echo "PDS mounted on $LOOP_DEV"
}

if [ -f /data/pds.img ]; then
	#delete old pds image that may have broken permissions
	rm -f /data/pds.img
fi

if [ ! -f $PDS_FILE ] ; then
	#make a copy of pds in /data
	dd if=/dev/block/mmcblk1p7 of=$PDS_FILE bs=4096

	#mount the fake pds
	mount_pds_image

	cd /pds
	#find and change moto users and groups
	$BB_STATIC find /pds -user 9000 -o -user 9003 -o -user 9004 -o -user 9007 -exec chown 1000 {} \;
	$BB_STATIC find /pds -group 9000 -o -group 9003 -o -group 9004 -o -group 9007 -o -group 9009 -exec chgrp 1000 {} \;

	echo "PDS Backed up, permissions fixed and mounted"

	if [ -d /data/battd ] ; then
		cd /data/battd
		$BB_STATIC find -user 9000 -exec chown 1000 {} \;
		$BB_STATIC find -group 9000 -exec chgrp 1000 {} \;
	fi

else

	#mount the existing pds backup
	mount_pds_image

	if [ -d /pds/public ] ; then
		echo "PDS partition mounted from data image."
	fi
fi
