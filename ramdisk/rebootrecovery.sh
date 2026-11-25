#!/sbin/sh
#
# TWRP runs /sbin/rebootrecovery.sh right before rebooting to recovery
# (TWFunc::tw_reboot(rb_recovery) -> check_and_run_script()).
#
# The bootstrap only enters recovery when /cache/recovery/bootmode.conf reads
# "recovery", so request it here. The recovery's TARGET_RECOVERY_PRE_COMMAND
# cannot: libcutils runs it through system() (/system/bin/sh) and /system is
# not mounted in TWRP, so it fails and the bootstrap shows its splash instead.

BOOTMODE_CONF=/cache/recovery/bootmode.conf

if [ -d /cache/recovery ]; then
	echo recovery > "$BOOTMODE_CONF"
	sync
fi

exit 0
