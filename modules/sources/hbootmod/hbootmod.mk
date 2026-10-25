# Opt in on the make command line (also used by bootstrap/bootstrap.mk).
.PHONY: hbootmod-install-force
hbootmod-install-force:

# Recopy on mode switches even when the selected input has an older timestamp.
# PRODUCT_COPY_FILES supplies the sole installation recipe in either mode.
$(PRODUCT_OUT)/system/bootstrap/modules/hbootmod.ko: hbootmod-install-force

ifeq ($(HBOOTMOD_FROM_SOURCE),true)
HBOOTMOD_SOURCE := $(DEVICE_PATH)/modules/sources/hbootmod
HBOOTMOD_OUT := $(PRODUCT_OUT)/obj/HBOOTMOD

# BoardConfig is parsed before the Android kernel target variables are defined.
# Use the concrete kernel image path to wait for the full kernel build, including
# generated headers and symbol versions, even for a standalone hbootmod build.
.PHONY: ext_modules
ext_modules: $(KERNEL_OUT)/arch/arm/boot/$(BOARD_KERNEL_IMAGE_NAME)

.PHONY: hbootmod
hbootmod: $(HBOOTMOD_OUT)/hbootmod.ko

# Kbuild handles incremental compilation through the shared ext_modules target.
# Keep the packaging input in PRODUCT_OUT without staging another source tree.
$(HBOOTMOD_OUT)/hbootmod.ko: ext_modules
	@test -s $(HBOOTMOD_SOURCE)/hbootmod.ko
	$(hide) mkdir -p $(HBOOTMOD_OUT)
	$(hide) cmp -s $(HBOOTMOD_SOURCE)/hbootmod.ko $@ || cp $(HBOOTMOD_SOURCE)/hbootmod.ko $@
endif
