# Required tools and blobs for bootstrap
DEVICE_PATH := device/motorola/shadow
include $(all-subdir-makefiles)

# Ramdisk
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/ramdisk/ueventd.mapphone_cdma.rc:root/ueventd.mapphone_cdma.rc \
	$(DEVICE_PATH)/ramdisk/init.usb.rc:root/init.usb.rc \
	$(DEVICE_PATH)/ramdisk/init.mapphone_cdma.rc:root/init.mapphone_cdma.rc \
	$(DEVICE_PATH)/ramdisk/fstab.mapphone_cdma:root/fstab.mapphone_cdma

# Ramdisk-recovery
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/recovery/twrp.fstab:recovery/root/etc/twrp.fstab

# Bootstrap scripts
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/bootstrap/script/2nd-boot.sh:system/bootstrap/script/2nd-boot.sh \
	$(DEVICE_PATH)/bootstrap/script/pdsbackup.sh:system/bootstrap/script/pdsbackup.sh

# Bootstrap 2nd-boot files
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/bootstrap/2nd-boot/devtree:system/bootstrap/2nd-boot/devtree \
	$(DEVICE_PATH)/bootstrap/2nd-boot/hboot.cfg:system/bootstrap/2nd-boot/hboot.cfg \
	$(DEVICE_PATH)/bootstrap/2nd-boot/hboot_recovery.cfg:system/bootstrap/2nd-boot/hboot_recovery.cfg \
	$(DEVICE_PATH)/bootstrap/2nd-boot/zImage-recovery:system/bootstrap/2nd-boot/zImage-recovery

# Bootstrap Binaries
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/bootstrap/binary/adbd:system/bootstrap/binary/adbd \
	$(DEVICE_PATH)/bootstrap/binary/busybox:system/bootstrap/binary/busybox \
	$(DEVICE_PATH)/bootstrap/binary/hbootuser:system/bootstrap/binary/hbootuser \
	$(DEVICE_PATH)/bootstrap/binary/logwrapper:system/bin/logwrapper \
	$(DEVICE_PATH)/bootstrap/binary/logwrapper.bin:system/bin/logwrapper.bin \
	$(DEVICE_PATH)/bootstrap/binary/safestrapmenu:system/bootstrap/binary/safestrapmenu

# Bootstrap Images
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/bootstrap/images/background-blank.png:system/bootstrap/images/background-blank.png \
	$(DEVICE_PATH)/bootstrap/images/background-def.png:system/bootstrap/images/background-def.png

# Bootstrap Modules
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/bootstrap/modules/hbootmod.ko:system/bootstrap/modules/hbootmod.ko \
	$(DEVICE_PATH)/bootstrap/modules/jbd2.ko:system/bootstrap/modules/jbd2.ko \
	$(DEVICE_PATH)/bootstrap/modules/ext4.ko:system/bootstrap/modules/ext4.ko

# Generated Files
PRODUCT_COPY_FILES += \
	$(OUT)/ramdisk-recovery.img:system/bootstrap/2nd-boot/ramdisk-recovery \
	$(OUT)/ramdisk.img:system/bootstrap/2nd-boot/ramdisk \
	$(OUT)/kernel:system/bootstrap/2nd-boot/zImage
