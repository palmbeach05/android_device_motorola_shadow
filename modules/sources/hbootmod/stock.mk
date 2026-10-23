# Dedicated stock-kernel build. Never use the custom kernel's KERNEL_OUT here.
HBOOTMOD_SOURCE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
HBOOTMOD_OUT ?= $(abspath out/stock-hbootmod)
HBOOTMOD_MODULE := $(HBOOTMOD_OUT)/hbootmod.ko

.PHONY: hbootmod_source hbootmod_stock_force
hbootmod_source: $(HBOOTMOD_MODULE)

# Always recheck external prerequisites and rebuild, including when switching
# between prebuilt and source packaging in an existing Android output tree.
$(HBOOTMOD_MODULE): hbootmod_stock_force
	+$(hide) MAKE="$(MAKE)" sh $(HBOOTMOD_SOURCE_DIR)/build-stock.sh \
		"$(HBOOTMOD_SOURCE_DIR)" "$(HBOOTMOD_OUT)" \
		"$(HBOOTMOD_STOCK_SOURCE)" "$(HBOOTMOD_STOCK_OUT)" \
		"$(HBOOTMOD_STOCK_REVISION)" "$(HBOOTMOD_STOCK_CONFIG)" \
		"$(HBOOTMOD_STOCK_CROSS_COMPILE)"
