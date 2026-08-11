# Copyright (C) 2013 The Android Open Source Project
# Copyright (C) 2026 The LineageOS Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# This file sets variables that control the way modules are built
# thorughout the system. It should not be used to conditionally
# disable makefiles (the proper mechanism to control what gets
# included in a build is to use PRODUCT_PACKAGES in a product
# definition file).
#

# WARNING: This line must come *before* including the proprietary
# variant, so that it gets overwritten by the parent (which goes
# against the traditional rules of inheritance).

# Inherit from the proprietary version if it exists
-include vendor/motorola/shadow-common/shadow-vendor.mk

DEVICE_PATH := device/motorola/shadow

# --- CPU & Architecture ---
TARGET_ARCH									:= arm
TARGET_BOARD_PLATFORM						:= omap3
TARGET_CPU_ABI								:= armeabi-v7a
TARGET_CPU_ABI2								:= armeabi
TARGET_ARCH_VARIANT							:= armv7-a-neon
TARGET_ARCH_VARIANT_CPU						:= cortex-a8
TARGET_CPU_VARIANT							:= cortex-a8
TARGET_ARCH_VARIANT_FPU						:= neon
TARGET_ARCH_HAVE_NEON						:= true
TARGET_ARCH_LOWMEM							:= true

# --- Bootloader & Board ---
TARGET_BOOTLOADER_BOARD_NAME				:= shadow
TARGET_NO_BOOTLOADER						:= true
TARGET_NO_RADIOIMAGE						:= true
TARGET_NO_PREINSTALL						:= true
TARGET_NO_KERNEL							:= false
TARGET_OMAP3								:= true
TARGET_NO_RECOVERY							:= false
TARGET_RECOVERY_OUT							:= $(PRODUCT_OUT)/recovery
BOARD_USES_RECOVERY_AS_BOOT					:= false

# --- Legacy Compatibility Hacks ---
COMMON_GLOBAL_CFLAGS						+= -DTARGET_OMAP3 -DOMAP_COMPAT -DBINDER_COMPAT -DUSES_AUDIO_LEGACY
COMMON_GLOBAL_CFLAGS						+= -DNEEDS_VECTORIMPL_SYMBOLS -DSYSTEMUI_PBSIZE_HACK=1
TARGET_GLOBAL_CFLAGS						+= -DREFBASE_JB_MR1_COMPAT_SYMBOLS
COMMON_GLOBAL_CFLAGS						+= -DWORKAROUND_BUG_10194508=1 -DHAS_CONTEXT_PRIORITY -DDONT_USE_FENCE_SYNC
BOARD_USE_KINETO_COMPATIBILITY				:= true
BOARD_USES_LEGACY_RIL						:= true
BOARD_USE_LEGACY_SENSORS_FUSION				:= false
BUILD_BROKEN_PYTHON_IS_PYTHON2				:= true

# --- Toolchain & Optimization ---
TARGET_GLOBAL_CFLAGS						+= -mtune=cortex-a8 -mfpu=neon -mfloat-abi=softfp
TARGET_GLOBAL_CPPFLAGS						+= -mtune=cortex-a8 -mfpu=neon -mfloat-abi=softfp

# --- Connectivity (Wi-Fi & Bluetooth) ---
BOARD_WLAN_DEVICE							:= wl12xx_mac80211
BOARD_SOFTAP_DEVICE							:= wl12xx_mac80211
USES_TI_MAC80211							:= true
COMMON_GLOBAL_CFLAGS						+= -DUSES_TI_MAC80211
WPA_SUPPLICANT_VERSION						:= VER_0_8_X
BOARD_WPA_SUPPLICANT_DRIVER					:= NL80211
BOARD_WPA_SUPPLICANT_PRIVATE_LIB			:= lib_driver_cmd_wl12xx
BOARD_HOSTAPD_DRIVER						:= NL80211
BOARD_HOSTAPD_PRIVATE_LIB					:= lib_driver_cmd_wl12xx
PRODUCT_WIRELESS_TOOLS						:= true
BOARD_WIFI_SKIP_CAPABILITIES				:= true
BOARD_HAVE_BLUETOOTH						:= true
BOARD_BLUETOOTH_BDROID_BUILDCFG_INCLUDE_DIR	:= $(DEVICE_PATH)/bluetooth
TARGET_USE_BLUEDROID_STACK					:= true
WIFI_DRIVER_MODULE_PATH						:= "/system/lib/modules/wl12xx_sdio.ko"
WIFI_DRIVER_MODULE_NAME						:= "wl12xx_sdio"

# Init & Healthd HAL
TARGET_INIT_VENDOR_LIB						:= libinit_omap3
TARGET_LIBINIT_DEFINES_FILE					:= $(DEVICE_PATH)/init/init_omap3.c
BOARD_HAL_STATIC_LIBRARIES					:= libhealthd.omap3

# --- Multimedia & Graphics ---
HARDWARE_OMX								:= true
TARGET_USE_OMX_RECOVERY						:= true
TARGET_USE_OMAP_COMPAT						:= true
BUILD_WITH_TI_AUDIO							:= 1
BUILD_PV_VIDEO_ENCODERS						:= 1
BOARD_USES_AUDIO_LEGACY						:= true
TARGET_PROVIDES_LIBAUDIO					:= true
PRODUCT_PREBUILT_WEBVIEWCHROMIUM			:= no
TARGET_FORCE_CPU_TYPE						:= true

BOARD_VOLD_EMMC_SHARES_DEV_MAJOR			:= true
BOARD_UMS_LUNFILE							:= "/sys/class/android_usb/f_mass_storage/lun/file"
TARGET_USE_CUSTOM_LUN_FILE_PATH				:= "/sys/class/android_usb/f_mass_storage/lun/file"
BOARD_HARDWARE_CLASS						:= $(DEVICE_PATH)/cmhw/

USE_OPENGL_RENDERER							:= true
BOARD_USE_YUV422I_DEFAULT_COLORFORMAT		:= true
MAX_EGL_CACHE_SIZE							:= 2097152
MAX_EGL_CACHE_KEY_SIZE						:= 4096

# Triple Buffering
NUM_FRAMEBUFFER_SURFACE_BUFFERS				:= 3
TARGET_RUNNING_WITHOUT_SYNC_FRAMEWORK		:= true

# Release tool
TARGET_PROVIDES_RELEASETOOLS				:= true
TARGET_RELEASETOOL_OTA_FROM_TARGET_SCRIPT	:= build/tools/releasetools/ota_from_target_files --device_specific $(DEVICE_PATH)/releasetools/shadow-common_ota_from_target_files.py
TARGET_SYSTEMIMAGE_USE_SQUISHER				:= true

# --- Recovery & TWRP ---
RECOVERY_VARIANT							:= twrp
RECOVERY_BOOTABLE_PATH						:= bootable/recovery-twrp
TARGET_RECOVERY_UI_LIB						:= librecovery_ui_default
TARGET_RECOVERY_FSTAB						:= $(DEVICE_PATH)/recovery/twrp.fstab
RECOVERY_FSTAB_VERSION						:= 2
TARGET_RECOVERY_INITRC						:= $(DEVICE_PATH)/ramdisk/init.recovery.shadow.rc
BOARD_HAS_LARGE_FILESYSTEM					:= true
# DEVICE_RESOLUTION							:= 480x854
TW_THEME									:= portrait_hdpi
RECOVERY_GRAPHICS_USE_LINELENGTH			:= true
TARGET_RECOVERY_PIXEL_FORMAT				:= "BGRA_8888"
TW_EXCLUDE_MTP								:= true
TW_NO_USB_STORAGE							:= true
TW_INTERNAL_STORAGE_PATH					:= "/data"
TW_INTERNAL_STORAGE_MOUNT_POINT				:= "data"
TW_EXTERNAL_STORAGE_PATH					:= "/external_sd"
TW_EXTERNAL_STORAGE_MOUNT_POINT				:= "external_sd"
BOARD_HAS_NO_SELECT_BUTTON					:= true
TW_HAS_NO_RECOVERY_PARTITION				:= true
TW_HAS_NO_BOOT_PARTITION					:= true
TARGET_USERIMAGES_USE_EXT4					:= true
TW_NO_REBOOT_BOOTLOADER						:= true
TW_NO_REBOOT_RECOVERY						:= true
TW_BRIGHTNESS_PATH							:= /sys/class/leds/lcd-backlight/brightness
TW_MAX_BRIGHTNESS							:= 255
TW_CUSTOM_CPU_TEMP_PATH						:= "/sys/devices/platform/cpcap_battery/power_supply/battery/temp"
ALLOW_MISSING_DEPENDENCIES					:= true
TARGET_RECOVERY_DEVICE_MODULES				+= recovery_tzdata recovery_led_charger
TARGET_NO_SEPARATE_RECOVERY					:= true
TW_EXCLUDE_SUPERSU							:= true
TW_EXCLUDE_ENCRYPTED_BACKUPS				:= true
TARGET_RECOVERY_UPDATER_EXTRA_LIBS			+= libext4_utils_static libsparse_static libz
TW_INPUT_BLACKLIST							:= "h2w"
TARGET_RECOVERY_PRE_COMMAND 				:= "echo recovery > /cache/recovery/bootmode.conf; sync;"
TARGET_RECOVERY_PRE_COMMAND_CLEAR_REASON 	:= true
BOARD_ALWAYS_INSECURE						:= true

# --- Kernel Configuration ---
TARGET_KERNEL_SOURCE						:= kernel/motorola/shadow
BOARD_KERNEL_IMAGE_NAME						:= zImage
TARGET_KERNEL_CONFIG						:= shadow_cm11_defconfig
TARGET_PREBUILT_RECOVERY_KERNEL				:= $(DEVICE_PATH)/bootstrap/2nd-boot/zImage-recovery
KERNEL_OUT									:= $(abspath $(TARGET_OUT_INTERMEDIATES)/KERNEL_OBJ)

BOARD_COMMON_KERNEL_CMDLINE	:= \
	console=/dev/null \
	mem=499M \
	init=/init \
	omapfb.vram=0:4M \
	usbcore.old_scheme_first=y \
	androidboot.bootloader=3004 \
	androidboot.mode=normal
BOARD_KERNEL_CMDLINE := \
	$(BOARD_COMMON_KERNEL_CMDLINE) \
	panic=30 \
	mmcparts=mmcblk1:p20(kpanic) \
	cpcap_charger_enabled=n
BOARD_RECOVERY_KERNEL_CMDLINE := \
	$(BOARD_COMMON_KERNEL_CMDLINE) \
	cpcap_charger_enabled=y \
	androidboot.serialno=DROIDX

# Toolchain setup for GCC 4.4.3
TARGET_KERNEL_CUSTOM_TOOLCHAIN				:= arm-eabi-4.4.3
KERNEL_TOOLCHAIN							:= $(ANDROID_BUILD_TOP)/prebuilt/linux-x86/toolchain/$(TARGET_KERNEL_CUSTOM_TOOLCHAIN)/bin
KERNEL_CROSS_COMPILE 						:= $(KERNEL_TOOLCHAIN)/arm-eabi-
KERNEL_MAKE_FLAGS							+= ARCH=arm CROSS_COMPILE=$(KERNEL_CROSS_COMPILE) CC=$(KERNEL_CROSS_COMPILE)gcc

# --- Custom Module Build Logic ---
TARGET_KERNEL_MODULES_EXT					:= $(DEVICE_PATH)/modules/sources/
TARGET_KERNEL_MODULES						:= ext_modules WLAN_MODULES hboot

ext_modules:
	$(hide) mkdir -p $(KERNEL_MODULES_OUT)
	$(hide) mkdir -p $(DEVICE_PATH)/modules/prebuilt
	@echo "--- Compiling and Gathering Shadow Modules ---"
	$(hide) $(MAKE) -C $(TARGET_KERNEL_MODULES_EXT) modules KERNEL_DIR=$(KERNEL_OUT) $(KERNEL_MAKE_FLAGS)
	$(hide) find $(TARGET_KERNEL_MODULES_EXT) -name "*.ko" -exec cp -v {} $(DEVICE_PATH)/modules/prebuilt/ \;
	$(hide) cp -v $(KERNEL_OUT)/drivers/video/output.ko $(KERNEL_MODULES_OUT)/ || echo "output.ko not found in KERNEL_OUT"
	$(hide) find $(TARGET_KERNEL_MODULES_EXT) -name "*.ko" -exec cp -v {} $(KERNEL_MODULES_OUT)/ \;
	$(hide) find $(KERNEL_MODULES_OUT)/ -name "*.ko" -exec $(KERNEL_CROSS_COMPILE)strip --strip-unneeded {} + || true
	$(hide) find $(KERNEL_MODULES_OUT) -name "*.ko" -exec chmod 0644 {} \;

WLAN_MODULES:
	$(hide) mkdir -p $(KERNEL_MODULES_OUT)
	$(hide) $(MAKE) clean -C hardware/ti/wlan/mac80211/compat_wl12xx
	$(hide) $(MAKE) -C hardware/ti/wlan/mac80211/compat_wl12xx \
		KERNEL_DIR=$(abspath $(KERNEL_OUT)) \
		KLIB=$(abspath $(KERNEL_OUT)) \
		KLIB_BUILD=$(abspath $(KERNEL_OUT)) \
		ARCH=arm \
		CROSS_COMPILE=$(KERNEL_CROSS_COMPILE) \
		EXTRA_CFLAGS="-fno-strict-aliasing"
	$(hide) cp hardware/ti/wlan/mac80211/compat_wl12xx/compat/compat.ko $(KERNEL_MODULES_OUT)/
	$(hide) cp hardware/ti/wlan/mac80211/compat_wl12xx/net/mac80211/mac80211.ko $(KERNEL_MODULES_OUT)/
	$(hide) cp hardware/ti/wlan/mac80211/compat_wl12xx/net/wireless/cfg80211.ko $(KERNEL_MODULES_OUT)/
	$(hide) cp hardware/ti/wlan/mac80211/compat_wl12xx/drivers/net/wireless/wl12xx/wl12xx.ko $(KERNEL_MODULES_OUT)/
	$(hide) cp hardware/ti/wlan/mac80211/compat_wl12xx/drivers/net/wireless/wl12xx/wl12xx_sdio.ko $(KERNEL_MODULES_OUT)/
	$(hide) find $(KERNEL_MODULES_OUT) -name "*.ko" -exec $(KERNEL_CROSS_COMPILE)strip --strip-unneeded {} + || true
	$(hide) find $(KERNEL_MODULES_OUT) -name "*.ko" -exec chmod 0644 {} \;

hboot: $(INSTALLED_KERNEL_TARGET)
	@echo "--- Building Shadow Hboot Bootstrap ---"
	$(hide) mkdir -p $(PRODUCT_OUT)/system/bootstrap/2nd-boot
	$(hide) echo "$(BOARD_KERNEL_CMDLINE)" > $(PRODUCT_OUT)/system/bootstrap/2nd-boot/cmdline
	$(hide) echo "$(BOARD_RECOVERY_KERNEL_CMDLINE)" > $(PRODUCT_OUT)/system/bootstrap/2nd-boot/cmdline-recovery
	$(hide) $(MAKE) -C $(DEVICE_PATH)/bootstrap/hboot $(KERNEL_MAKE_FLAGS)
	$(hide) cp $(DEVICE_PATH)/bootstrap/hboot/hboot.bin $(PRODUCT_OUT)/system/bootstrap/2nd-boot/
	$(hide) cp $(KERNEL_OUT)/arch/arm/boot/zImage $(PRODUCT_OUT)/system/bootstrap/2nd-boot/zImage
	$(hide) cp $(DEVICE_PATH)/bootstrap/2nd-boot/zImage-recovery $(PRODUCT_OUT)/system/bootstrap/2nd-boot/zImage-recovery
	@echo "--- Bootstrap files placed in $(PRODUCT_OUT)/system/bootstrap/2nd-boot ---"

$(INSTALLED_SYSTEMIMAGE_TARGET): ext_modules WLAN_MODULES hboot
