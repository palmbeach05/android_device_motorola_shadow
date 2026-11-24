How to compile Droid X kernel modules
------------------------------------

These external kernel modules require the Droid X kernel tree :

It is available at https://github.com/palmbeach05/shadow-kernel

Add to your repo manifest \<project path="kernel/motorola/shadow-kernel" name="palmbeach05/shadow-kernel" />

---

"repo sync" and then, in root of your android repo :

    . build/envsetup.sh
    breakfast shadow
    
    make kernel
    make device_modules

---

PS : Do not make menuconfig, or use make in kernel tree, if you have an error reporting
the kernel source is not clean, type before :

    make kernel_clean

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:0c7b78f0e0e1caabdcfeeb59f9feeeb853e971169f821fd88f9aed480d6ead97 -->

Bootstrap hbootmod
------------------

The stock kernel loads `system/bootstrap/modules/hbootmod.ko` before the
custom kernel starts. Set `HBOOTMOD_STOCK_KERNEL_BUILD` to the absolute path of
a prepared ARM kernel build with the sources and configuration for the stock
kernel on the device (including module unloading). Build that kernel first so
the configured headers and `Module.symvers` are available. Set the variable in
the Android build environment or on the make command line.

During system image assembly, Android builds the sources in
`modules/sources/hbootmod` in a separate intermediates directory against
that stock kernel and installs the resulting module. The regular
`ext_modules` target builds against the custom kernel and supplies the
modules for `system/lib/modules`.

<!-- /coderabbit-ai-generated:v1 -->
