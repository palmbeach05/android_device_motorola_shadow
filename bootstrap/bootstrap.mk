# Required tools and blobs for bootstrap
COMMON_PATH = device/moto/shadow-common
include $(all-subdir-makefiles)

# Ramdisk
PRODUCT_COPY_FILES += \
	$(COMMON_PATH)/ramdisk/ueventd.mapphone_cdma.rc:root/ueventd.mapphone_cdma.rc \
	$(COMMON_PATH)/ramdisk/init.usb.rc:root/init.usb.rc \
	$(COMMON_PATH)/ramdisk/init.mapphone_cdma.rc:root/init.mapphone_cdma.rc \
	$(COMMON_PATH)/ramdisk/fstab.mapphone_cdma:root/fstab.mapphone_cdma \

# scripts
PRODUCT_COPY_FILES += \
	$(COMMON_PATH)/bootstrap/script/2nd-boot.sh:system/bootstrap/script/2nd-boot.sh \
	$(COMMON_PATH)/bootstrap/script/pdsbackup.sh:system/bootstrap/script/pdsbackup.sh \

# prebuilt binaries
PRODUCT_COPY_FILES += \
	$(COMMON_PATH)/bootstrap/binary/adbd:system/bootstrap/binary/adbd \
	$(COMMON_PATH)/bootstrap/binary/logwrapper:system/bin/logwrapper \
	$(COMMON_PATH)/bootstrap/binary/logwrapper.bin:system/bin/logwrapper.bin \
	$(COMMON_PATH)/bootstrap/binary/hbootuser:system/bootstrap/binary/hbootuser \
	$(COMMON_PATH)/bootstrap/binary/safestrapmenu:system/bootstrap/binary/safestrapmenu \
	$(COMMON_PATH)/bootstrap/binary/busybox:system/bootstrap/binary/busybox \
	$(COMMON_PATH)/bootstrap/modules/hbootmod.ko:system/bootstrap/modules/hbootmod.ko \
	$(COMMON_PATH)/bootstrap/2nd-boot/hboot.cfg:system/bootstrap/2nd-boot/hboot.cfg \
	$(COMMON_PATH)/bootstrap/2nd-boot/hboot_recovery.cfg:system/bootstrap/2nd-boot/hboot_recovery.cfg \
	$(COMMON_PATH)/bootstrap/2nd-boot/zImage-recovery:system/bootstrap/2nd-boot/zImage-recovery \
	$(COMMON_PATH)/twrp.fstab:recovery/root/etc/twrp.fstab \
	$(COMMON_PATH)/bootstrap/modules/jbd2.ko:system/bootstrap/modules/jbd2.ko \
	$(COMMON_PATH)/bootstrap/modules/ext4.ko:system/bootstrap/modules/ext4.ko \
	$(COMMON_PATH)/bootstrap/images/background-def.png:system/bootstrap/images/background-def.png \
	$(COMMON_PATH)/bootstrap/images/background-blank.png:system/bootstrap/images/background-blank.png \
	$(OUT)/ramdisk-recovery.img:system/bootstrap/2nd-boot/ramdisk-recovery \
	$(OUT)/ramdisk.img:system/bootstrap/2nd-boot/ramdisk \
	$(OUT)/kernel:system/bootstrap/2nd-boot/zImage \

