#
# Copyright (C) 2011 The Android Open Source Project
# Licensed under the Apache License, Version 2.0
#

# Product configuration for Motorola Droid X (shadow)

# --- Path Definitions ---
DEVICE_PATH := device/motorola/shadow
COMMON_PATH := device/motorola/shadow-common
PERMISSION_PATH := frameworks/native/data/etc

# --- Inheritances (Most specific first) ---
$(call inherit-product, device/motorola/shadow-common/bootstrap/bootstrap.mk)
$(call inherit-product, device/common/gps/gps_eu_supl.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
$(call inherit-product, frameworks/native/build/phone-hdpi-512-dalvik-heap.mk)

DEVICE_PACKAGE_OVERLAYS += device/motorola/shadow-common/overlay

# System properties
-include $(LOCAL_PATH)/system_prop.mk

PLATFORM_BASE_OS := 4.4.4
PRODUCT_PROPERTY_OVERRIDES += \
	dalvik.vm.debug.alloc=0 \
	hwui.use.blacklist=true \
	ro.input.noresample=1 \
	persist.sys.root_access=3 \
	keyguard.no_require_sim=true

PRODUCT_DEFAULT_PROPERTY_OVERRIDES += \
	persist.sys.usb.config=mass_storage
	
# --- Boot Animation & Display ---
TARGET_SCREEN_HEIGHT := 854
TARGET_SCREEN_WIDTH := 480
PRODUCT_AAPT_CONFIG := normal hdpi
PRODUCT_AAPT_PREF_CONFIG := hdpi

# --- Hardware Blobs & Firmware ---
# --- Connectivity (WLAN/BT Firmware) ---
PRODUCT_COPY_FILES += \
    $(COMMON_PATH)/prebuilt/etc/firmware/ti-connectivity/wl127x-fw-5-mr.bin:system/etc/firmware/ti-connectivity/wl127x-fw-4-mr.bin \
    $(COMMON_PATH)/prebuilt/etc/firmware/ti-connectivity/wl127x-fw-5-plt.bin:system/etc/firmware/ti-connectivity/wl127x-fw-4-plt.bin \
    $(COMMON_PATH)/prebuilt/etc/firmware/ti-connectivity/wl127x-fw-5-sr.bin:system/etc/firmware/ti-connectivity/wl127x-fw-4-sr.bin \
    $(COMMON_PATH)/prebuilt/etc/firmware/ti-connectivity/wl1271-nvs.bin:system/etc/firmware/ti-connectivity/wl1271-nvs.bin \
    $(COMMON_PATH)/prebuilt/etc/firmware/TIInit_7.6.15.bts:system/etc/firmware/TIInit_7.6.15.bts \
    $(COMMON_PATH)/prebuilt/etc/wifi/wpa_supplicant_overlay.conf:system/etc/wifi/wpa_supplicant_overlay.conf \
    $(COMMON_PATH)/prebuilt/etc/wifi/p2p_supplicant_overlay.conf:system/etc/wifi/p2p_supplicant_overlay.conf \
    $(COMMON_PATH)/prebuilt/bin/wifical.sh:system/bin/wifical.sh

# --- Input Configuration (Key Layouts & IDC) ---
PRODUCT_COPY_FILES += \
    $(COMMON_PATH)/prebuilt/usr/idc/internal.idc:system/usr/idc/lm3530_led.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/internal.idc:system/usr/idc/accelerometer.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/internal.idc:system/usr/idc/compass.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/internal.idc:system/usr/idc/light-prox.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/internal.idc:system/usr/idc/proximity.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/sholes-keypad.idc:system/usr/idc/sholes-keypad.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/cpcap-key.idc:system/usr/idc/cpcap-key.idc \
    $(COMMON_PATH)/prebuilt/usr/idc/qtouch-touchscreen.idc:system/usr/idc/qtouch-touchscreen.idc \
    $(COMMON_PATH)/prebuilt/usr/qwerty.kl:system/usr/keylayout/qtouch-touchscreen.kl \
    $(COMMON_PATH)/prebuilt/usr/keypad.kl:system/usr/keylayout/sholes-keypad.kl \
    $(COMMON_PATH)/prebuilt/usr/keypad.kl:system/usr/keylayout/cdma_shadow-keypad.kl \
    $(COMMON_PATH)/prebuilt/usr/cpcap-key.kl:system/usr/keylayout/cpcap-key.kl \
    $(COMMON_PATH)/prebuilt/usr/keychars/cpcap-key.kcm:system/usr/keychars/cpcap-key.kcm

# --- Permissions Files ---
PRODUCT_COPY_FILES += \
	$(PERMISSION_PATH)/android.hardware.bluetooth.xml:system/etc/permissions/android.hardware.bluetooth.xml \
	$(PERMISSION_PATH)/android.hardware.camera.flash-autofocus.xml:system/etc/permissions/android.hardware.camera.flash-autofocus.xml \
	$(PERMISSION_PATH)/android.hardware.camera.xml:system/etc/permissions/android.hardware.camera.xml \
	$(PERMISSION_PATH)/android.hardware.location.gps.xml:system/etc/permissions/android.hardware.location.gps.xml \
	$(PERMISSION_PATH)/android.hardware.sensor.accelerometer.xml:system/etc/permissions/android.hardware.sensor.accelerometer.xml \
	$(PERMISSION_PATH)/android.hardware.sensor.compass.xml:system/etc/permissions/android.hardware.sensor.compass.xml \
	$(PERMISSION_PATH)/android.hardware.sensor.light.xml:system/etc/permissions/android.hardware.sensor.light.xml \
	$(PERMISSION_PATH)/android.hardware.sensor.proximity.xml:system/etc/permissions/android.hardware.sensor.proximity.xml \
	$(PERMISSION_PATH)/android.hardware.telephony.cdma.xml:system/etc/permissions/android.hardware.telephony.cdma.xml \
	$(PERMISSION_PATH)/android.hardware.touchscreen.multitouch.distinct.xml:system/etc/permissions/android.hardware.touchscreen.multitouch.distinct.xml \
	$(PERMISSION_PATH)/android.hardware.touchscreen.multitouch.xml:system/etc/permissions/android.hardware.touchscreen.multitouch.xml \
	$(PERMISSION_PATH)/android.hardware.wifi.xml:system/etc/permissions/android.hardware.wifi.xml \
	$(PERMISSION_PATH)/android.hardware.wifi.direct.xml:system/etc/permissions/android.hardware.wifi.direct.xml \
	$(PERMISSION_PATH)/handheld_core_hardware.xml:system/etc/permissions/handheld_core_hardware.xml \
	$(PERMISSION_PATH)/android.hardware.usb.accessory.xml:system/etc/permissions/android.hardware.usb.accessory.xml \
	$(PERMISSION_PATH)/android.hardware.usb.host.xml:system/etc/permissions/android.hardware.usb.host.xml

# --- Product Packages ---
# Audio & Connectivity
PRODUCT_PACKAGES += \
    audio.a2dp.default \
    audio.r_submix.default \
    libaudiohw_legacy \
    libaudioutils \
    libbluedroid \
    libbt-vendor

# Networking & Wireless
PRODUCT_PACKAGES += \
    dhcpcd.conf \
    hostapd.conf \
    iw \
    libnl_2 \
    regulatory.bin \
    ti_wfd_libs \
    wpa_supplicant.conf

# Motorola Specifics & Hardware Bringup
PRODUCT_PACKAGES += \
    calibrator \
    charge_only_mode \
    dspexec \
    libfnc \
    mot_boot_mode \
    uim-sysfs

# Shadow Apps & UI Tools
PRODUCT_PACKAGES += \
    DXParts \
    HwaSettings \
    MotoFM \
    MotoFMService \
    Torch \
    safestrapmenu

# Webview & System Components
PRODUCT_PACKAGES += \
    com.android.future.usb.accessory \
    libwebview_shadow \
    webviewchromium
	
# Media & OMX
PRODUCT_PACKAGES += \
	libbridge libLCML libOMX_Core libstagefrighthw \
	libOMX.TI.AAC.encode libOMX.TI.AAC.decode libOMX.TI.AMR.decode libOMX.TI.AMR.encode \
	libOMX.TI.WBAMR.encode libOMX.TI.MP3.decode libOMX.TI.WBAMR.decode \
	libOMX.TI.Video.Decoder libOMX.TI.Video.encoder libOMX.TI.JPEG.Encoder \
	libOMX.TI.720P.Encoder

# --- Localization ---
PRODUCT_LOCALES := \
    en_US en_GB en_IN fr_FR it_IT de_DE es_ES \
    hu_HU uk_UA zh_CN zh_TW ru_RU nl_NL se_SV \
    cs_CZ pl_PL pt_BR da_DK ko_KR el_GR ro_RO \
    iw_IL ar_EG sv_SE he_IL fi_FI bg_BG hr_HR \
    sr_RS sl_SI tr_TR
	
# --- System Scripts & Configs ---
PRODUCT_COPY_FILES += \
    $(COMMON_PATH)/prebuilt/etc/init.d/08backlight:system/etc/init.d/08backlight \
    $(COMMON_PATH)/prebuilt/etc/init.d/90multitouch:system/etc/init.d/90multitouch \
    $(COMMON_PATH)/prebuilt/etc/init.d/09overclock:system/etc/init.d/09overclock \
    $(COMMON_PATH)/prebuilt/etc/init.d/98netflix:system/etc/init.d/98netflix \
    $(COMMON_PATH)/prebuilt/etc/sysctl.conf:system/etc/sysctl.conf \
    $(COMMON_PATH)/prebuilt/etc/gpsconfig.xml:system/etc/gpsconfig.xml \
    $(COMMON_PATH)/prebuilt/etc/location.cfg:system/etc/location.cfg \
    $(COMMON_PATH)/prebuilt/etc/media_codecs.xml:system/etc/media_codecs.xml \
    $(COMMON_PATH)/prebuilt/etc/audio_policy.conf:system/etc/audio_policy.conf \
    $(COMMON_PATH)/prebuilt/etc/apns-conf.xml:system/etc/apns-conf.xml

# --- Time Zone data for recovery ---
PRODUCT_COPY_FILES += \
    bionic/libc/zoneinfo/tzdata:recovery/root/system/usr/share/zoneinfo/tzdata \
    bionic/libc/zoneinfo/tzdata:recovery/root/usr/share/zoneinfo/tzdata
