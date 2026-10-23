#!/bin/sh
# Inputs must describe the running stock kernel, not the second-boot kernel.
set -eu
fail() { echo "hbootmod: $*" >&2; exit 1; }
[ "$#" -eq 7 ] || fail 'expected source, output, stock source/output/revision/config and compiler prefix'
module_source=$1
module_out=$2
stock_source=$3
stock_out=$4
stock_revision=$5
stock_config=$6
cross_compile=$7

case "$module_out" in
    /*) ;;
    *) fail 'HBOOTMOD_OUT must be an absolute path' ;;
esac
[ -n "$stock_source" ] && [ -n "$stock_out" ] &&
    [ -n "$stock_revision" ] && [ -n "$stock_config" ] &&
    [ -n "$cross_compile" ] || fail 'set all HBOOTMOD_STOCK_* inputs; see modules/sources/README.md'
stock_source=$(cd "$stock_source" && pwd -P)
stock_out=$(cd "$stock_out" && pwd -P)
[ -f "$stock_source/Makefile" ] || fail 'stock kernel Makefile missing'
[ "$(git -C "$stock_source" rev-parse HEAD)" = "$stock_revision" ] ||
    fail 'stock source HEAD does not match the supplied full revision'
[ -z "$(git -C "$stock_source" status --porcelain --untracked-files=normal)" ] ||
    fail 'stock source must be clean; record all vendor changes in the supplied revision'
[ -f "$stock_config" ] || fail 'reference stock configuration missing'
cmp -s "$stock_config" "$stock_out/.config" || fail 'prepared .config differs from reference stock configuration'
grep -q '^CONFIG_ARM=y$' "$stock_out/.config" || fail 'stock configuration is not ARM'
grep -q '^CONFIG_MODULES=y$' "$stock_out/.config" || fail 'stock configuration disables modules'
[ -s "$stock_out/include/linux/autoconf.h" ] || fail 'prepared 2.6.32 autoconf.h missing'
[ -s "$stock_out/include/linux/utsrelease.h" ] || fail 'prepared utsrelease.h missing'
grep -Eq '^#define UTS_RELEASE "2\.6\.32\.9(["-])' "$stock_out/include/linux/utsrelease.h" ||
    fail 'prepared output is not stock 2.6.32.9'
[ -s "$stock_out/Module.symvers" ] || fail 'matching stock Module.symvers required (modules_prepare is insufficient)'
[ "$("${cross_compile}gcc" -dumpversion)" = 4.4.3 ] || fail 'initial baseline requires GCC 4.4.3'
case "$("${cross_compile}gcc" -dumpmachine)" in
    arm*) ;;
    *) fail 'cross-compiler must target ARM' ;;
esac

mkdir -p "$module_out"
module_out=$(cd "$module_out" && pwd -P)
module_parent=$(cd "$module_source/.." && pwd -P)
case "$module_out/" in
    "$stock_source/"*|"$stock_out/"*|"$module_parent/"*)
        fail 'module output must be outside the stock kernel trees and modules/sources' ;;
esac
# Temporary M= directory keeps Kbuild artifacts out of both the source checkout
# and the custom-kernel module tree. A failed build never publishes an output.
work=$(mktemp -d "$module_out/build.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
cp "$module_source/Makefile" "$module_source/"*.c "$module_source/"*.h "$module_source/"*.S "$work/"
"${MAKE:-make}" -C "$stock_source" O="$stock_out" ARCH=arm \
    CROSS_COMPILE="$cross_compile" CC="${cross_compile}gcc" M="$work" modules
[ -s "$work/hbootmod.ko" ] || fail 'Kbuild did not produce hbootmod.ko'
"${cross_compile}readelf" -h "$work/hbootmod.ko" | grep -Eq 'Machine:.*ARM' || fail 'output is not ARM ELF'
# Publish only after successful compilation, linking and the basic ELF check.
cp "$work/hbootmod.ko" "$module_out/hbootmod.ko.new"
mv -f "$module_out/hbootmod.ko.new" "$module_out/hbootmod.ko"
