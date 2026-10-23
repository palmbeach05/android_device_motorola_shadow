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


Stock-kernel bootstrap hbootmod (opt-in, boot verification pending)
----------------------------------------------------------------

This path is separate from `device_modules` and the custom 2.6.32.69
`KERNEL_OUT`. The parent module list deliberately does not select hbootmod.
No hbootmod runtime source, ioctl layouts, parameters, serial forwarding,
kernel/ramdisk selection, or other module build paths are changed.

The stock baseline is NOT yet established. This checkout supplies neither an
identified stock Motorola Shadow 2.6.32.9 source revision nor its verified
configuration, generated headers, matching exported symbols, or GCC 4.4.3
installation. The existing kernel URL above is not evidence of stock ABI
compatibility. Do not substitute the custom kernel output. Source packaging
remains disabled by default; the checked-in prebuilt is retained for rollback.
The available checkout is detached at 52f992f; no serial_number_fix ref was
available locally to verify the requested base or its supersession. Reconcile
this focused change with serial_number_fix before opening/merging the PR.
No changes from #13 to hbootuser or safestrapmenu are included.

Required inputs, supplied explicitly on the make command line:

- `HBOOTMOD_STOCK_SOURCE`: absolute path to a clean, tracked stock-compatible
  vendor kernel source checkout, including Motorola platform headers.
- `HBOOTMOD_STOCK_REVISION`: its full Git commit ID. Identify and record the
  revision corresponding to the running stock firmware; a matching version
  string alone is insufficient. Commit any required vendor patches first.
- `HBOOTMOD_STOCK_CONFIG`: absolute path to the reference configuration for
  that firmware (obtain /proc/config.gz if available, otherwise the vendor's
  verified configuration). Do not use shadow_cm11_defconfig.
- `HBOOTMOD_STOCK_OUT`: absolute path to a separately prepared output tree
  built from that revision/configuration. It must contain the matching .config,
  include/linux/autoconf.h, include/linux/utsrelease.h, architecture-generated
  headers, scripts, and Module.symvers from the matching complete stock kernel
  build. `modules_prepare` alone does not generate symbol CRCs. Preserve the
  complete stock release suffix and all ABI-relevant configuration options.
  Matching Module.symvers is required here even without CONFIG_MODVERSIONS, to
  give modpost the exported symbol inventory; with CONFIG_MODVERSIONS=y its
  CRCs must match the running kernel.
- `HBOOTMOD_STOCK_CROSS_COMPILE`: absolute ARM compiler prefix, initially
  /path/to/arm-eabi-4.4.3/bin/arm-eabi-. GCC 4.4.3 is enforced for this baseline;
  it does not prove ABI compatibility.
- `HBOOTMOD_OUT`: absolute, dedicated module output directory outside both
  kernel trees and outputs (and outside modules/sources). Do not share it
  between concurrent builds.

Once those inputs have been verified, prepare the separate stock output using
that source tree's documented build procedure. Typical commands, after setting
these shell variables to the verified paths/revision above, are:

```sh
cp "$HBOOTMOD_STOCK_CONFIG" "$HBOOTMOD_STOCK_OUT/.config"
make -C "$HBOOTMOD_STOCK_SOURCE" O="$HBOOTMOD_STOCK_OUT" ARCH=arm \
    CROSS_COMPILE="$HBOOTMOD_STOCK_CROSS_COMPILE" oldconfig
cmp "$HBOOTMOD_STOCK_CONFIG" "$HBOOTMOD_STOCK_OUT/.config"
make -C "$HBOOTMOD_STOCK_SOURCE" O="$HBOOTMOD_STOCK_OUT" ARCH=arm \
    CROSS_COMPILE="$HBOOTMOD_STOCK_CROSS_COMPILE" zImage modules
```

Resolve any configuration drift against the actual firmware before proceeding.
Do not edit vermagic, strip version sections, force-load, or disable compatibility
checks. The wrapper checks prerequisites but cannot establish their provenance.

From the Android source root, build only hbootmod with:

```sh
make -f device/motorola/shadow/modules/sources/hbootmod/stock.mk hbootmod_source \
    HBOOTMOD_STOCK_SOURCE="$HBOOTMOD_STOCK_SOURCE" \
    HBOOTMOD_STOCK_OUT="$HBOOTMOD_STOCK_OUT" \
    HBOOTMOD_STOCK_REVISION="$HBOOTMOD_STOCK_REVISION" \
    HBOOTMOD_STOCK_CONFIG="$HBOOTMOD_STOCK_CONFIG" \
    HBOOTMOD_STOCK_CROSS_COMPILE="$HBOOTMOD_STOCK_CROSS_COMPILE" \
    HBOOTMOD_OUT="$HBOOTMOD_OUT"
```

For Android packaging, after `. build/envsetup.sh` and `breakfast shadow`, use
`make systemimage` with the same six assignments plus
`HBOOTMOD_BUILD_FROM_SOURCE=true`. Use the same assignments on every build.
The product makefile runs before BoardConfig, so the output must be explicitly
set on the command line for packaging. Exactly one PRODUCT_COPY_FILES entry
selects system/bootstrap/modules/hbootmod.ko. The source entry depends on the
build rule, which always revalidates inputs and compiles the existing hbootmod
Kbuild object list in an isolated temporary M= directory. Failure stops the
build; it never falls back to the prebuilt. A previous output may remain after
failure but must not be used. No stripping or runtime changes are performed.

Before hardware testing, record the firmware identity, source commit, config
hash, compiler version, Module.symvers hash and the following results:

```sh
"${HBOOTMOD_STOCK_CROSS_COMPILE}readelf" -h "$HBOOTMOD_OUT/hbootmod.ko"
modinfo -F vermagic "$HBOOTMOD_OUT/hbootmod.ko"
modinfo -F vermagic device/motorola/shadow/bootstrap/modules/hbootmod.ko
"${HBOOTMOD_STOCK_CROSS_COMPILE}nm" -u "$HBOOTMOD_OUT/hbootmod.ko"
"${HBOOTMOD_STOCK_CROSS_COMPILE}readelf" -S "$HBOOTMOD_OUT/hbootmod.ko"
# When CONFIG_MODVERSIONS=y (kmod's dump-modversions option):
modprobe --dump-modversions "$HBOOTMOD_OUT/hbootmod.ko"
cmp "$HBOOTMOD_OUT/hbootmod.ko" \
    "$ANDROID_PRODUCT_OUT/system/bootstrap/modules/hbootmod.ko"
sha256sum "$HBOOTMOD_OUT/hbootmod.ko" \
    "$ANDROID_PRODUCT_OUT/system/bootstrap/modules/hbootmod.ko"
# bootstrap/bootstrap.mk retains its existing CRLF line endings:
git -c core.whitespace=cr-at-eol diff --check
```

Expect ELF32, little endian, ARM, relocatable; compare the full vermagic with
known stock modules and uname -r. Review undefined symbols against the matching
Module.symvers and resolve every modpost warning. With symbol versioning, check
that every imported CRC (including module_layout) matches that inventory.
Metadata checks do not establish runtime compatibility.

For dependency validation, make a temporary observable source change such as a
MODULE_INFO build marker, repeat the packaging command, confirm compilation
occurs, verify the marker with modinfo, and repeat cmp/hash checks on the staged
module. Revert the marker, rebuild and confirm its removal before deployment.
Also switch back to prebuilt packaging and verify cmp against the checked-in
prebuilt; clean the staged system/bootstrap/modules/hbootmod.ko before switching
to prebuilt if the Android copy rule retains a newer source-built destination.

Hardware and rollback merge gate
-------------------------------

Before installing a test image, save the known-good module and its hash off the
device and on removable storage, back up the working bootstrap/system setup,
and prepare a verified stock restore/reflash route usable if both system and
recovery fail. Recovery itself uses this module: do not depend solely on it for
rollback. Confirm access to the required bootloader/host tools and backups first.
Use a dedicated test device. Keep the checked-in prebuilt unchanged.

On hardware, capture logs proving all of the following with the source-built
module's hash recorded:

- It loads into the running stock 2.6.32.9 kernel without force options or
  compatibility errors, and /dev/hbootctrl appears.
- Normal and recovery handoffs complete with the existing kernels/ramdisks.
- The resulting Android and recovery report the expected device-specific stock
  HBoot serial. Record the stock identity first and compare /proc/cmdline,
  ro.serialno, ro.boot.serialno, and ro.ril.barcode; do not assume they agree.
- The UART handoff still works if the test setup supports it; otherwise record
  that check as unavailable.

Do not assume unloading is supported. To roll back, restore the saved prebuilt
at /system/bootstrap/modules/hbootmod.ko through the prepared recovery/restore
route, restore its permissions, verify its hash, and reboot through stock boot
rather than attempting rmmod/reload. For a rollback image, omit
HBOOTMOD_BUILD_FROM_SOURCE (or set false), clean the staged module, rebuild,
and verify the staged hash matches the prebuilt before installation.

Local validation: shell syntax and ShellCheck pass. A temporary fixture harness
exercised input staging/publication, rejection of 2.6.32.69, missing symbols,
configuration/compiler drift, and propagation of build failure without replacing
an existing output. That harness used a mock builder and the prebuilt ELF, not
a source compilation. This container also lacks make, so make-rule execution
could not be checked here. CRLF-aware diff whitespace checks pass.

No real stock compile/link, ARM output metadata/symbol
comparison, Android image packaging, rebuild/reinstall, or hardware boot checks
can be completed with the inputs in this checkout. All remain pending. Require
successful normal/recovery boot and serial evidence before merge. Updates,
buffer redesign, and optimizations belong in a separate stacked PR only after
that verified source-built baseline.
