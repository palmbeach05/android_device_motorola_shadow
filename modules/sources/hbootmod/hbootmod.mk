# Opt in on the make command line (also used by bootstrap/bootstrap.mk).
# HBOOTMOD_KERNEL_BUILD must be a prepared build tree for the loading stock kernel.
.PHONY: hbootmod-force
hbootmod-force:

# Recopy on mode switches even when the selected input has an older timestamp.
# PRODUCT_COPY_FILES supplies the sole installation recipe in either mode.
$(PRODUCT_OUT)/system/bootstrap/modules/hbootmod.ko: hbootmod-force

ifeq ($(HBOOTMOD_FROM_SOURCE),true)
HBOOTMOD_SOURCE := $(DEVICE_PATH)/modules/sources/hbootmod
HBOOTMOD_OUT := $(PRODUCT_OUT)/obj/HBOOTMOD
HBOOTMOD_CROSS_COMPILE ?= $(KERNEL_CROSS_COMPILE)
HBOOTMOD_KERNEL_BUILD := $(TARGET_KERNEL_SOURCE)

.PHONY: hbootmod
hbootmod: $(HBOOTMOD_OUT)/hbootmod.ko

# Always rebuild in an isolated staging directory. This also handles source
# removals and kernel input changes without leaving stale objects or modules.
$(HBOOTMOD_OUT)/hbootmod.ko: hbootmod-force
	$(hide) rm -rf $(HBOOTMOD_OUT)
	$(hide) mkdir -p $(HBOOTMOD_OUT)
	$(hide) cp $(HBOOTMOD_SOURCE)/Makefile $(HBOOTMOD_SOURCE)/*.c $(HBOOTMOD_SOURCE)/*.h $(HBOOTMOD_SOURCE)/*.S $(HBOOTMOD_OUT)/
	$(hide) $(MAKE) -C $(HBOOTMOD_KERNEL_BUILD) ARCH=arm CROSS_COMPILE=$(HBOOTMOD_CROSS_COMPILE) CC=$(HBOOTMOD_CROSS_COMPILE)gcc M=$(abspath $(HBOOTMOD_OUT)) modules
	@test -s $@
endif
