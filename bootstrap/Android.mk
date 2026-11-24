# Bootstrap loads this module before entering the custom kernel.
shadow_hbootmod_src := $(abspath $(call my-dir)/../modules/sources/hbootmod)
shadow_hbootmod_obj := $(abspath $(TARGET_OUT_INTERMEDIATES)/HBOOTMOD_STOCK)
shadow_hbootmod_installed := $(TARGET_OUT)/bootstrap/modules/hbootmod.ko

.PHONY: shadow_hbootmod_force
$(shadow_hbootmod_installed): PRIVATE_SOURCE := $(shadow_hbootmod_src)
$(shadow_hbootmod_installed): PRIVATE_OBJ := $(shadow_hbootmod_obj)
$(shadow_hbootmod_installed): shadow_hbootmod_force
	$(hide) test -n "$(HBOOTMOD_STOCK_KERNEL_BUILD)" || { echo "Set HBOOTMOD_STOCK_KERNEL_BUILD to the prepared Droid X stock kernel build directory" >&2; exit 1; }
	$(hide) rm -rf "$(PRIVATE_OBJ)"
	$(hide) mkdir -p "$(PRIVATE_OBJ)" "$(dir $@)"
	$(hide) cp "$(PRIVATE_SOURCE)/Makefile" "$(PRIVATE_SOURCE)"/*.[chS] "$(PRIVATE_OBJ)/"
	$(hide) $(MAKE) -C "$(HBOOTMOD_STOCK_KERNEL_BUILD)" M="$(PRIVATE_OBJ)" $(KERNEL_MAKE_FLAGS) modules
	$(hide) $(ACP) -fp "$(PRIVATE_OBJ)/hbootmod.ko" "$@"

$(shadow_hbootmod_installed): | $(ACP)
ALL_DEFAULT_INSTALLED_MODULES += $(shadow_hbootmod_installed)
