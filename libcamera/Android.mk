LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

# Allow the camera HAL to link even if the Overlay symbols are missing
LOCAL_ALLOW_UNDEFINED_SYMBOLS := true
LOCAL_MODULE_TAGS    := eng debug
LOCAL_MODULE_PATH    := $(TARGET_OUT_SHARED_LIBRARIES)/hw
LOCAL_MODULE         := camera.$(TARGET_BOOTLOADER_BOARD_NAME)
LOCAL_SRC_FILES      := cameraHal.cpp ShadowCameraWrapper.cpp
LOCAL_PRELINK_MODULE := false

LOCAL_C_INCLUDES += \
    $(ANDROID_BUILD_TOP)/frameworks/native/include \
    $(ANDROID_BUILD_TOP)/frameworks/av/include \
    $(ANDROID_BUILD_TOP)/frameworks/native/include/media/hardware \
    $(ANDROID_BUILD_TOP)/hardware/libhardware/include

LOCAL_SHARED_LIBRARIES += \
    liblog \
    libutils \
    libbinder \
    libcutils \
    libmedia \
    libhardware \
    libcamera_client \
    libdl \
    libgui \
    libui \
    libstlport \

include external/stlport/libstlport.mk

include $(BUILD_SHARED_LIBRARY)

