#!/usr/bin/env python3
"""Host-only regression harness; do not run in the inspection sandbox.

Run: python3 tools/tests/hbootmod_device_refs.py
Requires a Linux development host and a C compiler. Extracts the actual display
and UART preparation helpers, mocking device references, suspend and hardware.
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
                   'static void disable_dss(void)')
helpers += '\n' + function((source / 'emu_uart.c').read_text(),
                           'int activate_emu_uart(void)')
preamble = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef unsigned short u16;
typedef struct { int event; } pm_message_t;
struct device_driver { int unused; };
struct device { struct device_driver *driver; void *platform_data; };
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
static int events[32], event_count;
static int fail_transaction, transaction_count, warnings;
enum { LOOKUP = 1, SUSPEND_ENTER, SUSPEND_EXIT, READ, WRITE, MUX, PUT };
#define KERN_INFO ""
#define KERN_ALERT ""
#define KERN_ERR ""
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
    assert(event_count < 32);
    events[event_count++] = event;
}
static int find_my_dev(struct device *dev, void *data)
{ (void)dev; (void)data; return 1; }
static int find_device(struct device *dev, void *data)
{ (void)dev; (void)data; return 1; }
static struct device *device_find_child(struct device *parent, void *name,
                                       int (*match)(struct device *, void *))
{
    assert(parent == &platform_bus && !live);
    assert(!strcmp(name, uart ? "cpcap_usb" : "omapdss"));
    assert(match == (uart ? find_device : find_my_dev));
    record(LOOKUP);
    if (!found) return NULL;
    ++acquired;
    live = 1;
    return uart ? &devices->uart : &devices->display.dev;
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
static int cpcap_config_for_read(struct spi_device *spi, unsigned short reg,
                                 unsigned short *value)
{
    assert(live && spi == &devices->spi && reg == 18 && event_count == 1);
    record(READ);
    ++transaction_count;
    if (fail_transaction == transaction_count) return -5;
    *value = 0x1234;
    return 0;
}
static int cpcap_config_for_write(struct spi_device *spi, unsigned short reg,
                                  unsigned short value)
{
    assert(live && spi == &devices->spi);
    if (event_count == 14) assert(reg == 897 && value == 0x0101);
    else { assert(event_count == 15); assert(reg == 411 && value == 0x014C); }
    record(WRITE);
    ++transaction_count;
    return fail_transaction == transaction_count ?
           (transaction_count == 2 ? -110 : -121) : 0;
}
static void write_omap_mux_register(u16 offset, unsigned char mode,
                                     unsigned char input_en)
{
    assert(live);
    if (event_count < 14) {
        assert(event_count >= 2);
        assert(offset == 0x1A2 + (event_count - 2) * 2);
        assert(mode == 7 && input_en == 0);
    } else if (event_count == 16) {
        assert(offset == 0x19E && mode == 7 && input_en == 0);
    } else if (event_count == 17) {
        assert(offset == 0x1AA && mode == 2 && input_en == 0);
    } else {
        assert(event_count == 18);
        assert(offset == 0x1AC && mode == 2 && input_en == 1);
    }
    record(MUX);
}
'''
tests = r'''
static void scenario(int is_uart, int lookup, int driver, int callback, int data,
                     int result, int spi, int failure)
{
    int expected[32], count = 0, i, status = 0;
    int before_acquired = acquired, before_released = released;
    assert(!live && acquired == released);
    assert(!mprotect(devices, page_size, PROT_READ | PROT_WRITE));
    memset(devices, 0, sizeof(*devices));
    uart = is_uart; found = lookup; suspend_result = result; event_count = 0;
    devices->display.dev.driver = driver ? &devices->driver.driver : NULL;
    devices->driver.suspend = callback ? suspend_device : NULL;
    devices->uart.platform_data = data ? &devices->data : NULL;
    devices->data.spi = spi ? &devices->spi : NULL;
    fail_transaction = failure; transaction_count = warnings = 0;
    expected[count++] = LOOKUP;
    if (lookup) {
        if (uart && data && spi) {
            expected[count++] = READ;
            if (failure != 1) {
                for (i = 0; i < 12; ++i) expected[count++] = MUX;
                expected[count++] = WRITE;
                if (failure != 2) {
                    expected[count++] = WRITE;
                    if (failure != 3)
                        for (i = 0; i < 3; ++i) expected[count++] = MUX;
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
        else if (failure) status = failure == 1 ? -5 : failure == 2 ? -110 : -121;
        assert(activate_emu_uart() == status);
        assert(warnings == (status == 0));
    } else disable_dss();
    assert(acquired - before_acquired == !!lookup);
    assert(released - before_released == !!lookup);
    assert(!live && acquired == released);
    assert(event_count == count);
    assert(!memcmp(events, expected, count * sizeof(*events)));
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
        scenario(0, 0, 0, 0, 0, 0, 0, 0);
        scenario(0, 1, 0, 0, 0, 0, 0, 0);
        scenario(0, 1, 1, 0, 0, 0, 0, 0);
        scenario(0, 1, 1, 1, 0, 0, 0, 0);
        scenario(0, 1, 1, 1, 0, -5, 0, 0);
        scenario(1, 0, 0, 0, 0, 0, 0, 0);
        scenario(1, 1, 0, 0, 0, 0, 1, 0);
        scenario(1, 1, 0, 0, 1, 0, 0, 0);
        scenario(1, 1, 0, 0, 1, 0, 1, 1);
        scenario(1, 1, 0, 0, 1, 0, 1, 2);
        scenario(1, 1, 0, 0, 1, 0, 1, 3);
        scenario(1, 1, 0, 0, 1, 0, 1, 0);
    }
    assert(acquired == 1000 && released == 1000);
    assert(!munmap(devices, page_size));
    puts("hbootmod preparation device-reference checks passed");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='hbootmod-device-refs-') as directory:
    test_source = Path(directory) / 'device_refs.c'
    executable = Path(directory) / 'device_refs'
    test_source.write_text(preamble + helpers + tests)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu89', '-Wall', '-Wextra',
                    '-Werror', str(test_source), '-o', str(executable)],
                   check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=30)
