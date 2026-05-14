ifeq ($(TARGET_INIT_VENDOR_LIB),libinit_omap3)

LOCAL_PATH := $(call my-dir)
LIBINIT_OMAP_PATH := $(call my-dir)


UTC_DATE := $(shell date +%s)
DATE := $(shell date +%Y%m%d)

include $(CLEAR_VARS)
LOCAL_MODULE_TAGS := optional
LOCAL_C_INCLUDES := system/core/init
LOCAL_CFLAGS := -Wall -DBUILD_DATE=\"$(DATE)\"
LOCAL_SRC_FILES := init_omap3.c
LOCAL_MODULE := libinit_omap3
include $(BUILD_STATIC_LIBRARY)

endif
