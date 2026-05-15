#
# Copyright (C) 2012 The Android Open-Source Project
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

DEVICE_PATH := device/motorola/shadow

# Inherit some common CM stuff
$(call inherit-product, vendor/cm/config/common_full_phone.mk)
$(call inherit-product, vendor/cm/config/cdma.mk)
$(call inherit-product, $(DEVICE_PATH)/shadow.mk)

# --- Product Identity ---
PRODUCT_NAME := lineage_shadow
PRODUCT_DEVICE := shadow
PRODUCT_BRAND := Verizon
PRODUCT_MODEL := DROIDX
PRODUCT_MANUFACTURER := Motorola
PRODUCT_RELEASE_NAME := Motorola Droid X

UTC_DATE := $(shell date +%s)
DATE := $(shell date +%Y%m%d)

PRODUCT_BUILD_PROP_OVERRIDES += \
	BUILD_NUMBER=$(DATE) \
	BUILD_UTC_DATE=$(UTC_DATE) \
	PRODUCT_DEFAULT_LANGUAGE=en \
	PRODUCT_DEFAULT_REGION=US
