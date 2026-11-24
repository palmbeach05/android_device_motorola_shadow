#!/usr/bin/env python3
"""Host-only regression harness; do not run in the inspection sandbox.

Run: python3 tools/tests/hbootmod_device_refs.py
Requires a Linux development host and a C compiler. Extracts the actual display
and UART preparation helpers and name callbacks, mocking device references,
suspend and hardware.
No real device operations or boot transition are included. This does not verify
target compilation, driver-binding stability, or hardware behavior.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

source = Path(__file__).resolve().parents[2] / 'modules/sources/hbootmod'


def function(text, signature):
    pattern = r'\s+'.join(re.escape(part) for part in signature.split())
    start = re.search(pattern + r'[^\S\n]*\n\{', text).start()
    end = text.index('\n}', start) + 2
    return text[start:end]


helpers = function((source / 'hboot.c').read_text(),
                   'static int disable_dss(void)')
routing = (source / 'emu_uart.c').read_text()
for signature in ('static void write_omap_mux_register(u16 offset, u8 mode, u8 input_en)',
                  'void hboot_finish_emu_uart(struct hboot_uart_route *route, int keep)',
                  'int hboot_activate_emu_uart(struct hboot_uart_route *route)'):
    helpers += '\n' + function(routing, signature)
route_header = (source / 'emu_uart.h').read_text()
helpers += '\n' + function((source / 'hboot.c').read_text(),
                           'static int find_my_dev(struct device *dev, void *data)')
helpers += '\n' + function((source / 'emu_uart.c').read_text(),
                           'static int find_device(struct device *dev, void *data)')
preamble = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned int u32;
#define OMAP343X_CTRL_BASE 0x1000
typedef struct { int event; } pm_message_t;
struct device_driver { const char *name; };
struct device {
    struct device_driver *driver;
    void *platform_data;
    const char *name;
};
struct platform_device { struct device dev; };
struct platform_driver {
    struct device_driver driver;
    int (*suspend)(struct platform_device *, pm_message_t);
};
struct spi_device { int unused; };
struct cpcap_device { struct spi_device *spi; };
static struct device platform_bus;
static struct {
    struct platform_device display;
    struct platform_driver driver;
    struct device uart;
    struct cpcap_device data;
    struct spi_device spi;
} *devices;
static size_t page_size;
static int found, uart, live, acquired, released, suspend_result;
static int events[40], event_count;
static int fail_transaction, transaction_count, warnings;
enum { LOOKUP = 1, SUSPEND_ENTER, SUSPEND_EXIT, READ, WRITE, MUX, PUT };
#define KERN_INFO ""
#define KERN_ALERT ""
#define KERN_ERR ""
#define CTRL_DEVNAME "hbootctrl"
static void mock_printk(const char *message, ...)
{
    if (strstr(message, "WARNING: MiniUSB")) ++warnings;
}
#define printk mock_printk
#define to_platform_driver(p) \
    ((struct platform_driver *)((char *)(p) - offsetof(struct platform_driver, driver)))
#define to_platform_device(p) \
    ((struct platform_device *)((char *)(p) - offsetof(struct platform_device, dev)))
static void record(int event)
{
    assert(event_count < 40);
    events[event_count++] = event;
}
static const char *dev_name(struct device *dev) { return dev->name; }
static int find_my_dev(struct device *dev, void *data);
static int find_device(struct device *dev, void *data);
static struct device *device_find_child(struct device *parent, void *name,
                                       int (*match)(struct device *, void *))
{
    struct device *child = uart ? &devices->uart : &devices->display.dev;
    assert(parent == &platform_bus && !live);
    assert(!strcmp(name, uart ? "cpcap_usb" : "omapdss"));
    assert(match == (uart ? find_device : find_my_dev));
    record(LOOKUP);
    if (!found) return NULL;
    if (!match(child, name)) return NULL;
    ++acquired;
    live = 1;
    return child;
}
static void put_device(struct device *dev)
{
    assert(live && dev == (uart ? &devices->uart : &devices->display.dev));
    record(PUT);
    live = 0;
    ++released;
    /* Any later direct access to the device or derived pointers must fault. */
    assert(!mprotect(devices, page_size, PROT_NONE));
}
static int suspend_device(struct platform_device *dev, pm_message_t message)
{
    assert(live && dev == &devices->display && message.event == 0);
    record(SUSPEND_ENTER);
    assert(acquired == released + 1);
    record(SUSPEND_EXIT);
    return suspend_result;
}
static u16 cpcap_897, cpcap_411, pads[HBOOT_ULPI_PADS + 1];
static int cpcap_config_for_read(struct spi_device *spi, unsigned short reg,
                                 unsigned short *value)
{
    assert(live && spi == &devices->spi);
    assert(reg == (transaction_count == 0 ? 18 : transaction_count == 1 ? 897 : 411));
    record(READ);
    if (fail_transaction == ++transaction_count) return -EIO;
    *value = reg == 18 ? 0x1234 : reg == 897 ? cpcap_897 : cpcap_411;
    return 0;
}
static int cpcap_config_for_write(struct spi_device *spi, unsigned short reg,
                                  unsigned short value)
{
    assert(live && spi == &devices->spi);
    record(WRITE);
    /* Model a write that reaches the device before the SPI error arrives. */
    if (reg == 897) cpcap_897 = value;
    else { assert(reg == 411); cpcap_411 = value; }
    if (fail_transaction == ++transaction_count) return -EIO;
    return 0;
}
static u16 *mux_pad(u32 address)
{
    assert(live);
    assert(address == OMAP343X_CTRL_BASE + 0x19e ||
           (address >= OMAP343X_CTRL_BASE + 0x1a2 &&
            address < OMAP343X_CTRL_BASE + 0x1a2 + 2 * HBOOT_ULPI_PADS &&
            !(address & 1)));
    return &pads[address == OMAP343X_CTRL_BASE + 0x19e ? HBOOT_ULPI_PADS :
                 (address - OMAP343X_CTRL_BASE - 0x1a2) / 2];
}
static u16 omap_readw(u32 address) { return *mux_pad(address); }
static void omap_writew(u16 value, u32 address)
{
    *mux_pad(address) = value;
    record(MUX);
}
'''
tests = r'''
static void named_scenario(int is_uart, int lookup, int driver, int callback,
                           int data, int result, int spi, int failure,
                           const char *name)
{
    int expected[40], count = 0, i, status = 0;
    struct hboot_uart_route route;
    int keep = result == 0;
    int before_acquired = acquired, before_released = released;
    assert(!live && acquired == released);
    assert(!mprotect(devices, page_size, PROT_READ | PROT_WRITE));
    memset(devices, 0, sizeof(*devices));
    uart = is_uart; found = lookup; suspend_result = result; event_count = 0;
    devices->display.dev.name = devices->uart.name = name;
    devices->display.dev.driver = driver ? &devices->driver.driver : NULL;
    devices->driver.suspend = callback ? suspend_device : NULL;
    devices->uart.platform_data = data ? &devices->data : NULL;
    devices->data.spi = spi ? &devices->spi : NULL;
    cpcap_897 = 0x4321; cpcap_411 = 0xabcd;
    for (i = 0; i <= HBOOT_ULPI_PADS; ++i) pads[i] = 0x4200 + i;
    fail_transaction = failure; transaction_count = warnings = 0;
    /* Expected lookup outcome is independent of the production callback. */
    lookup = lookup && !strcmp(name, uart ? "cpcap_usb" : "omapdss");
    expected[count++] = LOOKUP;
    if (lookup) {
        if (uart && data && spi) {
            for (i = 1; i <= 3; ++i) {
                expected[count++] = READ;
                if (failure == i) break;
            }
            if (!failure || failure >= 4) {
                for (i = 0; i < HBOOT_ULPI_PADS; ++i) expected[count++] = MUX;
                expected[count++] = WRITE;
                if (failure != 4) expected[count++] = WRITE;
                if (!failure)
                    for (i = 0; i < 3; ++i) expected[count++] = MUX;
                if (failure || !keep) {
                    if (failure != 4) expected[count++] = WRITE;
                    expected[count++] = WRITE;
                    for (i = 0; i <= HBOOT_ULPI_PADS; ++i) expected[count++] = MUX;
                }
            }
        } else if (!uart && driver && callback) {
            expected[count++] = SUSPEND_ENTER;
            expected[count++] = SUSPEND_EXIT;
        }
        expected[count++] = PUT;
    }
    if (uart) {
        if (!lookup || !data || !spi) status = -ENODEV;
        else if (failure) status = -EIO;
        assert(hboot_activate_emu_uart(&route) == status);
        if (!status) {
            assert(live && released == before_released);
            hboot_finish_emu_uart(&route, keep);
        }
        assert(warnings == (!status && keep));
        if (!status && keep) {
            assert(cpcap_897 == 0x0101 && cpcap_411 == 0x014c);
            for (i = 0; i <= HBOOT_ULPI_PADS; ++i) {
                u16 expected_mux = i == 4 ? 0x1a : i == 5 ? 0x11a : 0x1f;
                assert(pads[i] == (0x4200 | expected_mux));
            }
        } else {
            assert(cpcap_897 == 0x4321 && cpcap_411 == 0xabcd);
            for (i = 0; i <= HBOOT_ULPI_PADS; ++i) assert(pads[i] == 0x4200 + i);
        }
    } else {
        if (!lookup || !driver) status = -ENODEV;
        else if (!callback) status = -EOPNOTSUPP;
        else status = result;
        assert(disable_dss() == status);
    }
    assert(acquired - before_acquired == !!lookup);
    assert(released - before_released == !!lookup);
    assert(!live && acquired == released);
    assert(event_count == count);
    assert(!memcmp(events, expected, count * sizeof(*events)));
}
static void scenario(int is_uart, int lookup, int driver, int callback, int data,
                     int result, int spi, int failure)
{
    named_scenario(is_uart, lookup, driver, callback, data, result, spi, failure,
                   is_uart ? "cpcap_usb" : "omapdss");
}
int main(void)
{
    int repeat;
    page_size = (size_t)sysconf(_SC_PAGESIZE);
    assert(sizeof(*devices) <= page_size);
    devices = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(devices != MAP_FAILED);
    for (repeat = 0; repeat < 100; ++repeat) {
        /* Rejected names must produce only LOOKUP, with no preparation or PUT. */
        named_scenario(0, 1, 1, 1, 0, 0, 0, 0, "omapdss");
        named_scenario(0, 1, 1, 1, 0, 0, 0, 0, "omap");
        named_scenario(0, 1, 1, 1, 0, 0, 0, 0, "omapdss_extra");
        named_scenario(0, 1, 1, 1, 0, 0, 0, 0, "unrelated");
        named_scenario(1, 1, 0, 0, 1, 0, 1, 0, "cpcap_usb");
        named_scenario(1, 1, 0, 0, 1, 0, 1, 0, "cpcap");
        named_scenario(1, 1, 0, 0, 1, 0, 1, 0, "cpcap_usb_extra");
        named_scenario(1, 1, 0, 0, 1, 0, 1, 0, "unrelated");
        scenario(0, 0, 0, 0, 0, 0, 0, 0);
        scenario(0, 1, 0, 0, 0, 0, 0, 0);
        scenario(0, 1, 1, 0, 0, 0, 0, 0);
        scenario(0, 1, 1, 1, 0, 0, 0, 0);
        scenario(0, 1, 1, 1, 0, -5, 0, 0);
        scenario(0, 1, 1, 1, 0, -ETIMEDOUT, 0, 0);
        scenario(1, 0, 0, 0, 0, 0, 0, 0);
        scenario(1, 1, 0, 0, 0, 0, 1, 0);
        scenario(1, 1, 0, 0, 1, 0, 0, 0);
        scenario(1, 1, 0, 0, 1, 0, 1, 1);
        scenario(1, 1, 0, 0, 1, 0, 1, 2);
        scenario(1, 1, 0, 0, 1, 0, 1, 3);
        scenario(1, 1, 0, 0, 1, 0, 1, 4);
        scenario(1, 1, 0, 0, 1, 0, 1, 5);
        scenario(1, 1, 0, 0, 1, -EIO, 1, 0);
        scenario(1, 1, 0, 0, 1, 0, 1, 0);
    }
    assert(acquired == 1600 && released == 1600);
    assert(!munmap(devices, page_size));
    puts("hbootmod preparation device-reference checks passed");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='hbootmod-device-refs-') as directory:
    test_source = Path(directory) / 'device_refs.c'
    executable = Path(directory) / 'device_refs'
    test_source.write_text(route_header + preamble + helpers + tests)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu89', '-Wall', '-Wextra',
                    '-Werror', str(test_source), '-o', str(executable)],
                   check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=30)
