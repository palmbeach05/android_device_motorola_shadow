#!/usr/bin/env python3
"""Host-only regression harness; do not run in the inspection sandbox.

Run: python3 tools/tests/hbootmod_locking.py
Requires a Linux development host with a 32-bit C library/compiler (-m32) and
pthreads, matching the source's 32-bit pointer storage. Uses actual buffer,
CRC, ioctl, write, UART configuration and boot-preparation code; mocks allocation,
user copies, MMIO, UART routing/display and the irreversible transition.
Does not validate kernel locking,
target compilation or hardware. Each executable has a timeout for deadlocks.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = root / 'modules/sources/hbootmod'


def without_includes(text):
    return re.sub(r'^#include .*\n', '', text, flags=re.MULTILINE)


def function(text, signature):
    pattern = r'\s+'.join(re.escape(part) for part in signature.split())
    start = re.search(pattern + r'[^\S\n]*\n\{', text).start()
    end = text.index('\n}', start) + 2
    return text[start:end]


buffers = without_includes((source / 'buffers.c').read_text())
start = buffers.index('/*\n * The device exposes')
end = buffers.index('static void init_abstract_buffer', start)
buffers = buffers[:start] + buffers[end:]
hboot = (source / 'hboot.c').read_text()
uart = '\n'.join(re.findall(r'^#define (?:MMU_\w+|UART_CLOCK_BASE_RATE|UART_POLL_\w+)\s+\w+',
                            hboot, re.MULTILINE)) + '\n'
uart += function(hboot, 'static int emu_uart_divisor(int uart_speed, uint16_t *divisor)')
uart += '\n' + function(hboot, 'static int uart_wait(uint32_t address, uint32_t mask, uint32_t ready)')
uart += '\n' + function(hboot, 'int reconfigure_emu_uart(int uart_speed)')
boot = function(hboot, 'static int hboot_boot(int handle) ')
# No disabled-interrupt code or assembly is compiled into the harness.
boot = boot[:boot.index('\t/* Disable preempting */')] + '''
    mock_transition(bootlist, listsize, boot_entry);
    free_high_pages((void *)l1_mem, 2);
    return -EBUSY;
}'''
control = function(hboot, 'static int hbootctrl_ioctl(struct inode *inode, struct file *file, unsigned int cmd, unsigned long arg) ')
control += '\n' + function(hboot, 'static int hbootctrl_write(struct file *file, const char __user *buf, size_t count, loff_t *ppos) ')
mutex = re.search(r'^static DEFINE_MUTEX\(hbootctrl_mutex\);$', hboot, re.MULTILINE).group()
# Hook after lookup and CRC finalization without changing the production source.
boot = boot.replace('boot_entry = get_bootentry(&bootsize, handle);',
                    'boot_entry = get_bootentry(&bootsize, handle); checkpoint(3);')
boot = boot.replace('bootlist = get_bootlist(&listsize, handle);',
                    'bootlist = fail_list ? NULL : get_bootlist(&listsize, handle); checkpoint(4);')

preamble = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/types.h>
#define __user
#define PAGE_SIZE 4096
#define min(a,b) ((a) < (b) ? (a) : (b))
#define KERN_INFO ""
#define KERN_ERR ""
#define CTRL_DEVNAME "hbootctrl"
#define printk(...) ((void)0)
struct inode { int unused; };
struct file { loff_t f_pos; };
#define DEFINE_MUTEX(name) pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
static pthread_mutex_t monitor = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static int attempts, completed, pause_at, paused, resume_op;
static void mutex_lock(pthread_mutex_t *m)
{
    pthread_mutex_lock(&monitor);
    ++attempts;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&monitor);
    assert(!pthread_mutex_lock(m));
}
static void mutex_unlock(pthread_mutex_t *m) { assert(!pthread_mutex_unlock(m)); }
static void checkpoint(int stage)
{
    pthread_mutex_lock(&monitor);
    if (pause_at == stage) {
        pause_at = 0;
        paused = 1;
        pthread_cond_broadcast(&changed);
        while (!resume_op) pthread_cond_wait(&changed, &monitor);
    }
    pthread_mutex_unlock(&monitor);
}
static size_t copy_budget = (size_t)-1;
static size_t copy_from_user(void *to, const void *from, size_t size)
{
    size_t copied = min(copy_budget, size);
    checkpoint(1);
    memcpy(to, from, copied);
    /* ARM copy_from_user() zero-pads the uncopied destination tail. */
    memset((char *)to + copied, 0, size - copied);
    if (copy_budget != (size_t)-1) copy_budget -= copied;
    return size - copied;
}
static int fail_pages, misalign_pages, fail_list, emu_uart = 115200, kill_dss = 1;
static unsigned int allocations, routing, display, transitions;
static unsigned int page_allocations, page_frees;
static unsigned int mem_allocations, mem_frees;
static unsigned int mem_attempts, page_attempts, l1_builds;
static int fail_mem_after = -1, fail_chunk_after = -1;
static int routing_status, display_status;
struct mmio_event { char operation; uint32_t address, value; };
static struct mmio_event mmio[128];
static unsigned int mmio_count;
/* Repeated busy reads and polling delays use counters, not trace entries. */
static int poll_stage = -1, slow_stage = -1, test_output;
static unsigned int ready_after, poll_reads[12], poll_delays, tx_position;
static void poll_reset(int stage, unsigned int after)
{
    poll_stage = -1; slow_stage = stage; ready_after = after; test_output = 0;
    memset(poll_reads, 0, sizeof(poll_reads));
    poll_delays = tx_position = mmio_count = 0;
}
static void mmio_record(char operation, uint32_t address, uint32_t value)
{
    assert(mmio_count < sizeof(mmio) / sizeof(mmio[0]));
    mmio[mmio_count++] = (struct mmio_event){ operation, address, value };
}
static uint32_t __raw_readl(uint32_t address)
{
    uint32_t value = address == 0xFB020058 ? 1 :
                     address == 0xFB020044 ? 0 : 0x100;
    if (address == 0xFB020058 || address == 0xFB020044) {
        unsigned int stage = address == 0xFB020058 ? 0 : tx_position;
        poll_stage = stage;
        ++poll_reads[stage];
        if ((int)stage == slow_stage && poll_reads[stage] <= ready_after)
            return address == 0xFB020058 ? 0 : 1;
    }
    mmio_record('r', address, value);
    return value;
}
static void __raw_writel(uint32_t value, uint32_t address)
{
    if (address == 0xFB020054) { test_output = 0; tx_position = 0; }
    if (address == 0xFB020000 && test_output) ++tx_position;
    mmio_record('w', address, value);
}
static void msleep(unsigned int duration)
{ test_output = 1; tx_position = 0; mmio_record('s', 0, duration); }
static void udelay(unsigned int duration)
{
    assert(duration == 1000 && poll_stage >= 0);
    ++poll_delays;
}
static uint32_t get_high_mem(size_t size)
{
    void *p;
    ++mem_attempts;
    ++allocations;
    if (fail_mem_after == 0) return 0;
    if (fail_mem_after > 0) --fail_mem_after;
    p = malloc(size);
    assert(p);
    ++mem_allocations;
    memset(p, 0xa5, size);
    return (uint32_t)p;
}
static void free_high_mem(void *p) { if (p) ++mem_frees; free(p); }
static uint32_t get_high_pages(unsigned int order)
{
    void *p;
    ++page_attempts;
    ++allocations;
    poll_reset(slow_stage, ready_after);
    checkpoint(2);
    if (fail_pages) return 0;
    if (fail_chunk_after == 0) return 0;
    if (fail_chunk_after > 0) --fail_chunk_after;
    assert(!posix_memalign(&p, 16384, PAGE_SIZE << order));
    ++page_allocations;
    memset(p, 0xa5, PAGE_SIZE << order);
    return (uint32_t)p + (misalign_pages ? 4 : 0);
}
static void free_high_pages(void *p, unsigned int order) { (void)order; ++page_frees; free((char *)p - (misalign_pages ? 4 : 0)); }
static void build_l1_table(uint32_t *table) { (void)table; ++l1_builds; }
static pthread_mutex_t hbootctrl_mutex;
static int hboot_activate_emu_uart(void)
{
    assert(pthread_mutex_trylock(&hbootctrl_mutex) == EBUSY);
    ++routing; checkpoint(5); return routing_status;
}
static int disable_dss(void)
{
    assert(pthread_mutex_trylock(&hbootctrl_mutex) == EBUSY);
    assert(!emu_uart || (routing && !routing_status && mmio_count));
    ++display; checkpoint(6); return display_status;
}
'''
# Headers supply the real ABI and declarations; allocator mocks above are static.
header = without_includes((source / 'buffers.h').read_text())
header += without_includes((source / 'hboot.h').read_text())
header = re.sub(r'^(?:uint32_t|void) (?:get_high_\w+|free_high_\w+)\([^;]+;\n', '', header, flags=re.MULTILINE)
crc = without_includes((source / 'crc32.c').read_text())
mock = r'''
static void snapshot_payload(int handle, char *data, size_t size);
static uint32_t contents_crc(int handle)
{
    size_t size = BUFFER_SIZE(buffers.bufs[handle].container.abstract);
    char *data = malloc(size);
    uint32_t checksum;
    assert(data);
    snapshot_payload(handle, data, size);
    checksum = crc32((const uint8_t *)data, size);
    free(data);
    return checksum;
}
static uint32_t expected_crc;
static int verify_snapshot;
static int verify_reuse, reuse_boot_handle;
static void *reuse_snapshot[MAX_BUFFERS_COUNT];
static void mock_transition(void *list, uint32_t count, bootfunc_t entry)
{
    assert(!emu_uart || (routing && !routing_status && mmio_count));
    assert(!kill_dss || (display && !display_status));
    ++transitions;
    checkpoint(7);
    assert(entry && list);
#ifdef HBOOT_VERIFY_CRC32
    /* Check every mocked preparation, including contenders after a paused boot.
     * Returning here only drives host tests; hardware handoff does not return. */
    for (uint32_t i = 0; i < count; ++i) {
        struct abstract_buffer *a = (void *)((uint32_t *)list)[i];
        for (int h = 0; h < buffers.used; ++h) {
            if (buffers.bufs[h].container.abstract == a && (a->attrs & B_ATTR_VERIFY))
                assert(a->checksum == contents_crc(h));
        }
    }
#endif
    if (verify_reuse) {
        int i, j, expected = 0;
        assert(entry == (bootfunc_t)buffers.bufs[reuse_boot_handle].container.plain->data);
        for (i = 0; i < MAX_BUFFERS_COUNT; ++i) {
            int matches = 0;
            assert(buffers.bufs[i].container.generic == reuse_snapshot[i]);
            for (j = 0; j < (int)count; ++j)
                if (((uint32_t *)list)[j] == (uint32_t)reuse_snapshot[i]) ++matches;
            if (reuse_snapshot[i] && i != reuse_boot_handle) {
                assert(matches == 1);
                ++expected;
            } else assert(matches == 0);
        }
        assert(count == (uint32_t)expected);
        verify_reuse = 0;
    }
    if (verify_snapshot) {
        struct abstract_buffer *a;
        assert(count == 1);
        a = (void *)((uint32_t *)list)[0];
#ifdef HBOOT_VERIFY_CRC32
        assert(a->checksum == expected_crc);
#endif
        assert(a->state == B_STAT_CREATED);
        assert(!memcmp(buffers.bufs[1].container.plain->data, "abcdefgh", 8));
        verify_snapshot = 0;
    }
}
'''
tests = r'''
static struct file first, second;
static void check_published(int handle)
{
    uint32_t count;
    struct abstract_buffer *a = buffers.bufs[handle].container.abstract;
    uint32_t checksum = a->checksum;
    mutex_lock(&hbootctrl_mutex);
    get_bootlist(&count, INVALID_BUFFER_HANDLE);
#ifdef HBOOT_VERIFY_CRC32
    if (a->attrs & B_ATTR_VERIFY)
        assert(a->checksum == contents_crc(handle));
    else
#endif
        assert(a->checksum == checksum);
    mutex_unlock(&hbootctrl_mutex);
}
static int ioctl_op(struct file *f, unsigned int cmd, unsigned long arg)
{ return hbootctrl_ioctl(NULL, f, cmd, arg); }
static int alloc(int type, int size, int attrs)
{
    struct hboot_buffer_req req = { 0, type, attrs, size, 0 };
    return ioctl_op(&first, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req);
}
static void reset(void)
{
    int i;
    for (i = 0; i < buffers.used; ++i)
        if (buffers.bufs[i].container.generic) assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, i));
    buffers_destroy();
    memset(&buffers, 0, sizeof(buffers));
    assert(!buffers_init());
    first.f_pos = second.f_pos = 0;
}
/* Compare every read, write and wait to the existing UART programming sequence. */
static void uart_programming(int rate, uint16_t divisor)
{
    struct mmio_event actual[128];
    unsigned int count, i;
    const char characters[] = "hbootmod!\r\n";
    uint16_t checked = 0;
    assert(!emu_uart_divisor(rate, &checked) && checked == divisor);
    poll_reset(-1, 0);
    assert(!reconfigure_emu_uart(rate));
    count = mmio_count;
    memcpy(actual, mmio, sizeof(actual));
    mmio_count = 0;
    mmio_record('r', MMU_CM_FCLKEN_PER, 0x100);
    mmio_record('w', MMU_CM_FCLKEN_PER, 0x900);
    mmio_record('r', MMU_CM_ICLKEN_PER, 0x100);
    mmio_record('w', MMU_CM_ICLKEN_PER, 0x900);
    mmio_record('r', MMU_UART3_BASE + 0x54, 0x100);
    mmio_record('w', MMU_UART3_BASE + 0x54, 0x102);
    mmio_record('r', MMU_UART3_BASE + 0x58, 1);
    mmio_record('r', MMU_UART3_BASE + 0x20, 0x100);
    mmio_record('w', MMU_UART3_BASE + 0x20, 0x107);
    mmio_record('r', MMU_UART3_BASE + 0x0C, 0x100);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 0xBF);
    mmio_record('r', MMU_UART3_BASE + 0x08, 0x100);
    mmio_record('w', MMU_UART3_BASE + 0x08, 0x110);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 0);
    mmio_record('r', MMU_UART3_BASE + 0x04, 0x100);
    mmio_record('w', MMU_UART3_BASE + 0x04, 0);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 0x80);
    mmio_record('w', MMU_UART3_BASE + 0x08, 6);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 0xBF);
    mmio_record('w', MMU_UART3_BASE + 0x00, divisor & 0xFF);
    mmio_record('w', MMU_UART3_BASE + 0x04, divisor >> 8);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 0xBF);
    mmio_record('w', MMU_UART3_BASE + 0x08, 0);
    mmio_record('w', MMU_UART3_BASE + 0x0C, 3);
    mmio_record('w', MMU_UART3_BASE + 0x20, 0);
    mmio_record('s', 0, 1);
    for (i = 0; i < sizeof(characters) - 1; ++i) {
        mmio_record('w', MMU_UART3_BASE, characters[i]);
        mmio_record('r', MMU_UART3_BASE + 0x44, 0);
    }
    assert(count == mmio_count);
    for (i = 0; i < count; ++i) {
        assert(actual[i].operation == mmio[i].operation);
        assert(actual[i].address == mmio[i].address);
        assert(actual[i].value == mmio[i].value);
    }
}
static void uart_rates(void)
{
    /* Integer rates jump across the 14-bit limit between 182 and 183 baud;
     * none yields exactly 0x3FFF with the existing clock constant. */
    const int invalid[] = { -1, INT_MIN, 1, 181, 182, 2995201, INT_MAX };
    const int valid[] = { 183, 184, 115200, 2995199, 2995200 };
    const uint16_t divisors[] = { 16367, 16278, 26, 1, 1 };
    unsigned int i;
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 1);
    for (i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        struct abstract_buffer before = *buffers.bufs[1].container.abstract;
        emu_uart = invalid[i];
        allocations = routing = display = transitions = mmio_count = 0;
        assert(reconfigure_emu_uart(emu_uart) == -EINVAL);
        assert(!mmio_count);
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EINVAL);
        assert(!allocations && !routing && !display && !transitions && !mmio_count);
        assert(!memcmp(&before, buffers.bufs[1].container.abstract, sizeof(before)));
        assert(!pthread_mutex_trylock(&hbootctrl_mutex));
        pthread_mutex_unlock(&hbootctrl_mutex);
    }
    mmio_count = 0;
    assert(reconfigure_emu_uart(0) == -EINVAL);
    assert(!mmio_count);
    emu_uart = 0;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    assert(allocations == 1 && !routing && display == 1 && transitions == 1);
    assert(!mmio_count);
    for (i = 0; i < sizeof(valid) / sizeof(valid[0]); ++i) {
        uart_programming(valid[i], divisors[i]);
        emu_uart = valid[i];
        allocations = routing = display = transitions = 0;
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
        assert(allocations == 1 && routing == 1 && display == 1 && transitions == 1);
        assert(mmio_count);
    }
    emu_uart = 115200;
}
/* Poll the production helper at every reset/transmit stage. Busy observations
 * are counted separately so the successful-path trace stays small and useful. */
static void uart_polling(void)
{
    struct mmio_event successful[128];
    unsigned int stage, i, delays, budget;
    unsigned int successful_count;
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
    emu_uart = 115200;
    kill_dss = 1;
    poll_reset(-1, 0);
    assert(!reconfigure_emu_uart(emu_uart));
    successful_count = mmio_count;
    memcpy(successful, mmio, sizeof(successful));
    assert(!poll_delays);
    budget = UART_POLL_TIMEOUT_US / UART_POLL_DELAY_US;
    assert(budget && budget * UART_POLL_DELAY_US == UART_POLL_TIMEOUT_US);
    for (stage = 0; stage < 12; ++stage) {
        /* Both ordinary delayed readiness and the final allowed observation. */
        for (delays = 2; ; delays = budget) {
            poll_reset(stage, delays);
            assert(!reconfigure_emu_uart(emu_uart));
            assert(poll_reads[stage] == delays + 1 && poll_delays == delays);
            assert(mmio_count == successful_count);
            for (i = 0; i < mmio_count; ++i) {
                assert(mmio[i].operation == successful[i].operation);
                assert(mmio[i].address == successful[i].address);
                assert(mmio[i].value == successful[i].value);
            }
            if (delays == budget) break;
        }
        {
            unsigned int allocated = page_allocations, freed = page_frees;
            unsigned int prefix = stage ? 26 + 2 * (stage - 1) + 1 : 6;
            poll_reset(stage, UINT_MAX);
            allocations = routing = display = transitions = 0;
            assert(ioctl_op(&first, HBOOT_BOOT, 0) == -ETIMEDOUT);
            assert(page_allocations == allocated + 1 && page_frees == freed + 1);
            assert(page_allocations == page_frees);
            assert(allocations == 1 && routing == 1 && !display && !transitions);
            assert(poll_reads[stage] == budget + 1 && poll_delays == budget);
            for (i = 0; i < stage; ++i) assert(poll_reads[i] == 1);
            for (i = stage + 1; i < 12; ++i) assert(!poll_reads[i]);
            /* Exact prefix: no later writes, characters or preparation. */
            assert(mmio_count == prefix);
            for (i = 0; i < prefix; ++i) {
                assert(mmio[i].operation == successful[i].operation);
                assert(mmio[i].address == successful[i].address);
                assert(mmio[i].value == successful[i].value);
            }
            assert(!pthread_mutex_trylock(&hbootctrl_mutex));
            pthread_mutex_unlock(&hbootctrl_mutex);
            assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, 0));
        }
    }
    /* Disabled preparation bypasses even a stuck reset condition. */
    emu_uart = 0;
    poll_reset(0, UINT_MAX);
    routing = display = transitions = 0;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    assert(!routing && display == 1 && transitions == 1 && !mmio_count);
    assert(!poll_delays);
    for (i = 0; i < 12; ++i) assert(!poll_reads[i]);
    /* Later mock success demonstrates control flow only, not hardware recovery. */
    poll_reset(-1, 0);
    emu_uart = 115200;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    assert(page_allocations == page_frees);
}
/* Mocked later success exercises control flow only; it is not hardware recovery. */
static void uart_routing_errors(void)
{
    const int errors[] = { -ENODEV, -EIO, -ETIMEDOUT, -121 };
    unsigned int i;
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
    emu_uart = 115200;
    for (i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
        unsigned int allocated = page_allocations, freed = page_frees;
        allocations = routing = display = transitions = mmio_count = 0;
        routing_status = errors[i];
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == errors[i]);
        assert(page_allocations == allocated + 1 && page_frees == freed + 1);
        assert(allocations == 1 && routing == 1);
        assert(!display && !transitions && !mmio_count);
        assert(!pthread_mutex_trylock(&hbootctrl_mutex));
        pthread_mutex_unlock(&hbootctrl_mutex);
    }
    routing_status = 0;
    allocations = routing = display = transitions = 0;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    assert(allocations == 1 && routing == 1 && display == 1 && transitions == 1);
    assert(mmio_count && page_allocations == page_frees);
    /* Disabled UART must not consult even a failing activation mock. */
    emu_uart = 0;
    routing_status = -EIO;
    allocations = routing = display = transitions = 0;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    assert(allocations == 1 && !routing && display == 1 && transitions == 1);
    assert(!mmio_count && page_allocations == page_frees);
    routing_status = 0;
    emu_uart = 115200;
}
/* A later successful mock call covers control flow, not hardware recovery. */
static void display_errors(void)
{
    const int errors[] = { -ENODEV, -EOPNOTSUPP, -EIO, -ETIMEDOUT };
    unsigned int i;
    int uart_enabled;
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
    routing_status = 0;
    kill_dss = 1;
    for (uart_enabled = 0; uart_enabled <= 1; ++uart_enabled) {
        emu_uart = uart_enabled ? 115200 : 0;
        for (i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
            unsigned int allocated = page_allocations, freed = page_frees;
            allocations = routing = display = transitions = mmio_count = 0;
            display_status = errors[i];
            assert(ioctl_op(&first, HBOOT_BOOT, 0) == errors[i]);
            assert(page_allocations == allocated + 1 && page_frees == freed + 1);
            assert(page_allocations == page_frees);
            assert(allocations == 1 && routing == (unsigned int)uart_enabled);
            assert(display == 1 && !transitions);
            assert(!!mmio_count == uart_enabled);
            assert(!pthread_mutex_trylock(&hbootctrl_mutex));
            pthread_mutex_unlock(&hbootctrl_mutex);
        }
        /* Disabled display preparation must not consult a failing mock. */
        kill_dss = 0;
        allocations = routing = display = transitions = mmio_count = 0;
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
        assert(allocations == 1 && routing == (unsigned int)uart_enabled);
        assert(!display && transitions == 1 && page_allocations == page_frees);
        kill_dss = 1;
        display_status = 0;
        allocations = routing = display = transitions = mmio_count = 0;
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
        assert(allocations == 1 && routing == (unsigned int)uart_enabled);
        assert(display == 1 && transitions == 1 && page_allocations == page_frees);
    }
    emu_uart = 115200;
}
static void snapshot_payload(int handle, char *data, size_t size)
{
    struct generic_buffer *buf = &buffers.bufs[handle];
    size_t offset;
    if (BUFFER_TYPE(buf->container.abstract) == B_TYPE_PLAIN) {
        memcpy(data, buf->container.plain->data, size);
    } else {
        struct scattered_buffer *sc = buf->container.scattered;
        for (offset = 0; offset < size; offset += sc->chunk_size)
            memcpy(data + offset, (void *)sc->chunks[offset / sc->chunk_size],
                   min(size - offset, (size_t)sc->chunk_size));
    }
}
/* Rejected writes must leave payload, CRC/state and both file positions intact. */
static void rejected_writes(int handle)
{
    char before[9000], after[9000];
    struct abstract_buffer metadata = *buffers.bufs[handle].container.abstract;
    loff_t first_pos = first.f_pos, second_pos = second.f_pos;
    snapshot_payload(handle, before, sizeof(before));
    assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == -EINVAL);
    assert(hbootctrl_write(&second, "abcdefgh", 8, &second.f_pos) == -EINVAL);
    snapshot_payload(handle, after, sizeof(after));
    assert(!memcmp(before, after, sizeof(before)));
    assert(!memcmp(&metadata, buffers.bufs[handle].container.abstract, sizeof(metadata)));
    assert(first.f_pos == first_pos && second.f_pos == second_pos);
}
/* Snapshot every live fixture, including packed typed metadata and bootlist.
 * For the misaligned fixture, inspect bytes through its original allocation. */
static void rejected_boot(int handle, void *original_payload)
{
    struct buffers_ctx before = buffers;
    unsigned char metadata[MAX_BUFFERS_COUNT][sizeof(struct scattered_buffer) +
                                               2 * sizeof(uint32_t)];
    char payload[MAX_BUFFERS_COUNT][CHUNK_SIZE + 17], actual[CHUNK_SIZE + 17];
    size_t metadata_size[MAX_BUFFERS_COUNT] = { 0 };
    void *plain_data[MAX_BUFFERS_COUNT] = { 0 };
    uint32_t bootlist[MAX_BUFFERS_COUNT];
    unsigned int mem_before = mem_attempts, pages_before = page_attempts;
    unsigned int mem_freed = mem_frees, pages_freed = page_frees;
    unsigned int built = l1_builds;
    loff_t first_pos = first.f_pos, second_pos = second.f_pos;
    int i, enabled, failure;
    memcpy(bootlist, buffers.bootlist, sizeof(bootlist));
    for (i = 0; i < buffers.used; ++i) {
        struct generic_buffer *buf = &buffers.bufs[i];
        if (!buf->container.generic) continue;
        switch (BUFFER_TYPE(buf->container.abstract)) {
        case B_TYPE_PLAIN:
            metadata_size[i] = sizeof(struct plain_buffer);
            plain_data[i] = i == handle && original_payload ?
                            original_payload : buf->container.plain->data;
            memcpy(payload[i], plain_data[i], BUFFER_SIZE(buf->container.abstract));
            break;
        case B_TYPE_SCATTERED:
            metadata_size[i] = sizeof(struct scattered_buffer) +
                              buf->container.scattered->allocated_chunks * sizeof(uint32_t);
            snapshot_payload(i, payload[i], BUFFER_SIZE(buf->container.abstract));
            break;
        case B_TYPE_NAND:
            metadata_size[i] = sizeof(struct nand_buffer);
            break;
        default:
            assert(0);
        }
        assert(metadata_size[i] <= sizeof(metadata[i]));
        memcpy(metadata[i], buf->container.generic, metadata_size[i]);
    }
    for (enabled = 0; enabled < 2; ++enabled) {
        emu_uart = enabled ? 115200 : 0;
        for (failure = 0; failure < 2; ++failure) {
            fail_pages = failure;
            allocations = routing = display = transitions = 0;
            poll_reset(-1, 0);
            assert(ioctl_op(&second, HBOOT_BOOT, (unsigned long)handle) == -EINVAL);
            assert(!allocations && mem_attempts == mem_before && page_attempts == pages_before);
            assert(mem_frees == mem_freed && page_frees == pages_freed && l1_builds == built);
            assert(!routing && !display && !transitions && !mmio_count && !poll_delays);
            for (i = 0; i < 12; ++i) assert(!poll_reads[i]);
            assert(!memcmp(&before, &buffers, sizeof(before)));
            assert(!memcmp(bootlist, buffers.bootlist, sizeof(bootlist)));
            assert(first.f_pos == first_pos && second.f_pos == second_pos);
            for (i = 0; i < buffers.used; ++i) {
                struct generic_buffer *buf = &buffers.bufs[i];
                if (!buf->container.generic) continue;
                assert(!memcmp(metadata[i], buf->container.generic, metadata_size[i]));
                if (BUFFER_TYPE(buf->container.abstract) == B_TYPE_NAND) continue;
                if (plain_data[i])
                    memcpy(actual, plain_data[i], BUFFER_SIZE(buf->container.abstract));
                else snapshot_payload(i, actual, BUFFER_SIZE(buf->container.abstract));
                assert(!memcmp(payload[i], actual, BUFFER_SIZE(buf->container.abstract)));
            }
            assert(!pthread_mutex_trylock(&hbootctrl_mutex));
            pthread_mutex_unlock(&hbootctrl_mutex);
        }
    }
    fail_pages = 0;
    emu_uart = 115200;
}
static void boot_buffer_preflight(void)
{
    int scattered, nand, freed, small[3], misaligned, i;
    void *original;
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, B_ATTR_VERIFY) == 0);
    scattered = alloc(B_TYPE_SCATTERED, CHUNK_SIZE + 17, B_ATTR_VERIFY);
    nand = alloc(B_TYPE_NAND, 123, B_ATTR_VERIFY);
    for (i = 0; i < 3; ++i) small[i] = alloc(B_TYPE_PLAIN, i + 1, B_ATTR_VERIFY);
    misaligned = alloc(B_TYPE_PLAIN, 8, B_ATTR_VERIFY);
    freed = alloc(B_TYPE_PLAIN, 8, 0);
    assert(scattered == 1 && nand == 2 && misaligned == 6 && freed == 7);
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, freed));
    assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, 0));
    assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == 8);
    first.f_pos = 3; second.f_pos = 7;
    rejected_boot(-1, NULL);
    rejected_boot(INT_MIN, NULL);
    rejected_boot(MAX_BUFFERS_COUNT, NULL);
    rejected_boot(INT_MAX, NULL);
    rejected_boot(buffers.used, NULL); /* Never allocated. */
    rejected_boot(freed, NULL);
    rejected_boot(scattered, NULL);
    rejected_boot(nand, NULL);
    for (i = 0; i < 3; ++i) rejected_boot(small[i], NULL);
    /* Test-only corruption under the operation mutex; restore before cleanup. */
    mutex_lock(&hbootctrl_mutex);
    original = buffers.bufs[misaligned].container.plain->data;
    buffers.bufs[misaligned].container.plain->data = (char *)original + 1;
    mutex_unlock(&hbootctrl_mutex);
    rejected_boot(misaligned, original);
    mutex_lock(&hbootctrl_mutex);
    buffers.bufs[misaligned].container.plain->data = original;
    mutex_unlock(&hbootctrl_mutex);
    /* A suitable buffer still reaches the allocator and preserves ENOMEM. */
    {
        unsigned int pages_before = page_attempts, mem_before = mem_attempts;
        unsigned int built = l1_builds, freed_before = page_frees;
        fail_pages = 1;
        allocations = routing = display = transitions = mmio_count = 0;
        assert(ioctl_op(&first, HBOOT_BOOT, 0) == -ENOMEM);
        assert(page_attempts == pages_before + 1 && mem_attempts == mem_before);
        assert(allocations == 1 && l1_builds == built && page_frees == freed_before);
        assert(!routing && !display && !transitions && !mmio_count);
        assert(!pthread_mutex_trylock(&hbootctrl_mutex));
        pthread_mutex_unlock(&hbootctrl_mutex);
        fail_pages = 0;
    }
}
static void selection(int type)
{
    char payload[9000], actual[9000];
    int h, unrelated, i;
    int invalid[3];
    reset();
    first.f_pos = 3; second.f_pos = 5;
    assert(buffers.handle == INVALID_BUFFER_HANDLE);
    assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == -EINVAL);
    assert(first.f_pos == 3 && second.f_pos == 5);
    h = alloc(type, sizeof(payload), B_ATTR_VERIFY);
    assert(h == 0 && buffers.handle == INVALID_BUFFER_HANDLE);
    rejected_writes(h);
    invalid[0] = -1; invalid[1] = buffers.used; invalid[2] = MAX_BUFFERS_COUNT;
    for (i = 0; i < 3; ++i) {
        assert(ioctl_op(&first, HBOOT_SELECT_BUFFER, invalid[i]) == -EINVAL);
        assert(buffers.handle == INVALID_BUFFER_HANDLE);
        assert(first.f_pos == 3 && second.f_pos == 5);
    }
    assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, h));
    assert(first.f_pos == 3 && second.f_pos == 0);
    assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
    assert(first.f_pos == 0 && second.f_pos == 0);
    memset(payload, 's', sizeof(payload));
    assert(hbootctrl_write(&first, payload, sizeof(payload), &first.f_pos) == sizeof(payload));
    second.f_pos = 7;
    for (i = 0; i < 3; ++i) {
        assert(ioctl_op(&second, HBOOT_SELECT_BUFFER, invalid[i]) == -EINVAL);
        assert(buffers.handle == h);
        assert(first.f_pos == sizeof(payload) && second.f_pos == 7);
    }
    unrelated = alloc(B_TYPE_PLAIN, 8, 0);
    assert(unrelated == 1 && buffers.handle == h);
    assert(!ioctl_op(&second, HBOOT_FREE_BUFFER, unrelated));
    assert(buffers.handle == h);
    assert(ioctl_op(&second, HBOOT_SELECT_BUFFER, unrelated) == -EINVAL);
    assert(first.f_pos == sizeof(payload) && second.f_pos == 7);
    assert(buffers.handle == h);
    assert(ioctl_op(&second, HBOOT_FREE_BUFFER, unrelated) == -1);
    assert(ioctl_op(&second, HBOOT_FREE_BUFFER, -1) == -1);
    assert(ioctl_op(&second, HBOOT_FREE_BUFFER, buffers.used) == -1);
    assert(ioctl_op(&second, HBOOT_FREE_BUFFER, MAX_BUFFERS_COUNT) == -1);
    assert(buffers.handle == h);
    /* Failed selections/frees preserve usable global selection. */
    assert(hbootctrl_write(&second, "abcdefgh", 8, &second.f_pos) == 8);
    memcpy(payload + 7, "abcdefgh", 8);
    snapshot_payload(h, actual, sizeof(actual));
    assert(!memcmp(actual, payload, sizeof(actual)));
    assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, h));
    assert(first.f_pos == sizeof(payload) && second.f_pos == 0);
    /* Free from the other descriptor invalidates the shared selection. */
    first.f_pos = 2; second.f_pos = 4;
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, h));
    assert(buffers.handle == INVALID_BUFFER_HANDLE);
    assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == -EINVAL);
    assert(hbootctrl_write(&second, "abcdefgh", 8, &second.f_pos) == -EINVAL);
    assert(ioctl_op(&second, HBOOT_SELECT_BUFFER, h) == -EINVAL);
    assert(first.f_pos == 2 && second.f_pos == 4);
    /* Fill the preferred last slot, then reuse the formerly selected slot. */
    assert(alloc(B_TYPE_PLAIN, 8, 0) == unrelated);
    assert(alloc(type, sizeof(payload), B_ATTR_VERIFY) == h);
    assert(buffers.handle == INVALID_BUFFER_HANDLE);
    rejected_writes(h);
    assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, h));
    assert(first.f_pos == 2 && second.f_pos == 0);
    assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
    memset(payload, 'r', sizeof(payload));
    assert(hbootctrl_write(&first, payload, sizeof(payload), &first.f_pos) == sizeof(payload));
    snapshot_payload(h, actual, sizeof(actual));
    assert(!memcmp(actual, payload, sizeof(actual)));
    check_published(h);
}
static void writes(int type)
{
    char data[9000];
    int h, result, limit;
    memset(data, 'x', sizeof(data));
    for (limit = 0; limit <= 9000; limit += 4500) {
        reset();
        h = alloc(type, sizeof(data), B_ATTR_VERIFY);
        assert(h == 0);
        assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
        copy_budget = limit;
        result = hbootctrl_write(&first, data, sizeof(data), &first.f_pos);
        assert(result == (limit ? limit : -EFAULT));
        assert(first.f_pos == limit);
        check_published(h);
        copy_budget = (size_t)-1;
        if (limit < 9000) {
            assert(hbootctrl_write(&first, data + limit, 9000 - limit, &first.f_pos) == 9000 - limit);
            assert(first.f_pos == 9000);
        }
        assert(hbootctrl_write(&first, data, 1, &first.f_pos) == -EINVAL);
        first.f_pos = -1;
        assert(hbootctrl_write(&first, data, 1, &first.f_pos) == -EINVAL);
    }
}

/* Direct preparation calls retain the same caller-held operation mutex. */
static void prepare_crc(int handle, const char *data, size_t size, int attrs)
{
    uint32_t count;
    uint32_t *list;
    struct abstract_buffer *a = buffers.bufs[handle].container.abstract;
    uint32_t checksum = a->checksum;
    char actual[9000];
    assert(size == BUFFER_SIZE(a) && size <= sizeof(actual));
    mutex_lock(&hbootctrl_mutex);
    for (int repeat = 0; repeat < 4; ++repeat) {
        list = get_bootlist(&count, 0);
        assert(count == 1 && list[0] == (uint32_t)a);
        assert(a->state == B_STAT_CREATED);
        snapshot_payload(handle, actual, size);
        assert(!memcmp(actual, data, size));
#ifdef HBOOT_VERIFY_CRC32
        if (attrs & B_ATTR_VERIFY) {
            assert(a->checksum == crc32((const uint8_t *)data, size));
            assert(a->checksum == contents_crc(handle));
        } else
#endif
            assert(a->checksum == checksum);
    }
    mutex_unlock(&hbootctrl_mutex);
}
static void crc_lifecycle(int type, int attrs)
{
    char data[9000], replacement[9000], actual[9000], expected[9000];
    int h, i;
    int offsets[] = { PAGE_SIZE - 1, PAGE_SIZE, PAGE_SIZE + 1, 2 * PAGE_SIZE + 3 };
    for (i = 0; i < (int)sizeof(data); ++i) {
        data[i] = (char)(i * 37 + 11);
        replacement[i] = (char)(i * 19 + 53);
    }
    for (int boundary = 0; boundary < 4; ++boundary) {
        reset();
        assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
        h = alloc(type, sizeof(data), attrs);
        assert(h == 1);
        for (int reuse = 0; reuse < 2; ++reuse) {
            /* Initialize every logical byte, including on slot reuse. */
            assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
            int prefix = offsets[boundary];
            assert(hbootctrl_write(&first, data, prefix, &first.f_pos) == prefix);
            assert(hbootctrl_write(&first, data + prefix, sizeof(data) - prefix,
                                   &first.f_pos) == sizeof(data) - prefix);
            if (type == B_TYPE_SCATTERED) {
                struct scattered_buffer *sc = buffers.bufs[h].container.scattered;
                size_t tail = sizeof(data) % sc->chunk_size;
                /* Allocation padding must never contribute to the checksum. */
                memset((char *)sc->chunks[sc->allocated_chunks - 1] + tail,
                       0xa5 + reuse, sc->chunk_size - tail);
            }
            prepare_crc(h, data, sizeof(data), attrs);
            /* Successful reselection resets this descriptor's position. */
            assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, h));
            assert(hbootctrl_write(&second, replacement, sizeof(replacement),
                                   &second.f_pos) == sizeof(replacement));
            prepare_crc(h, replacement, sizeof(replacement), attrs);
            assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
            assert(second.f_pos == sizeof(data));
            assert(hbootctrl_write(&first, data, prefix, &first.f_pos) == prefix);
            memcpy(expected, replacement, sizeof(expected));
            memcpy(expected, data, prefix);
            prepare_crc(h, expected, sizeof(expected), attrs);
            /* Another descriptor overlaps the first, crossing a chunk boundary. */
            second.f_pos = PAGE_SIZE - 7;
            assert(hbootctrl_write(&second, replacement, 31, &second.f_pos) == 31);
            memcpy(expected + PAGE_SIZE - 7, replacement, 31);
            prepare_crc(h, expected, sizeof(expected), attrs);
            for (int budget = 0; budget <= 17; budget += 17) {
                int offset = offsets[boundary];
                int length = min(PAGE_SIZE + 30, (int)sizeof(data) - offset);
                int zero_end = type == B_TYPE_PLAIN ? offset + length :
                    min((int)sizeof(data), ((offset + budget) / PAGE_SIZE + 1) * PAGE_SIZE);
                first.f_pos = offset;
                loff_t other_pos = second.f_pos;
                copy_budget = budget;
                assert(hbootctrl_write(&first, data, length, &first.f_pos) ==
                       (budget ? budget : -EFAULT));
                assert(first.f_pos == offset + budget && second.f_pos == other_pos);
                memcpy(expected + offset, data, budget);
                memset(expected + offset + budget, 0, zero_end - offset - budget);
                copy_budget = (size_t)-1;
                snapshot_payload(h, actual, sizeof(actual));
                assert(!memcmp(actual, expected, sizeof(actual)));
                prepare_crc(h, expected, sizeof(expected), attrs);
            }
            assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, h));
            assert(alloc(type, sizeof(data), attrs) == h);
        }
    }
}

static void initialized_checksum(struct abstract_buffer *a, int attrs)
{
    uint32_t expected = 0;
#ifdef HBOOT_VERIFY_CRC32
    if (attrs & B_ATTR_VERIFY) crc32_init_ctx(&expected);
#endif
    assert(a->checksum == expected);
}
static void initialization(int type, int attrs)
{
    const int sizes[] = { 1, CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1,
                          2 * CHUNK_SIZE + 17 };
    char expected[9000], actual[9000], dirty[9000];
    unsigned int i;
    memset(dirty, 0x6b, sizeof(dirty));
    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); ++i) {
        int size = sizes[i], h;
        reset();
        assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
        h = alloc(type, size, B_ATTR_VERIFY);
        assert(h == 1);
        initialized_checksum(buffers.bufs[h].container.abstract, B_ATTR_VERIFY);
        memset(expected, 0, size);
        snapshot_payload(h, actual, size);
        assert(!memcmp(actual, expected, size));
        /* Dirty the old payload and checksum before reusing its slot with
         * either verification setting. Allocator poison also covers fresh RAM. */
        assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
        assert(hbootctrl_write(&first, dirty, size, &first.f_pos) == size);
        buffers.bufs[h].container.abstract->checksum = 0x12345678;
        assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, h));
        for (int reuse = 0; reuse < 2; ++reuse) {
            assert(alloc(type, size, attrs) == h);
            initialized_checksum(buffers.bufs[h].container.abstract, attrs);
            memset(expected, 0, size);
            snapshot_payload(h, actual, size);
            assert(!memcmp(actual, expected, size));
            prepare_crc(h, expected, size, attrs);
            assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, h));
            first.f_pos = size / 2;
            assert(hbootctrl_write(&first, "xyz", 1, &first.f_pos) == 1);
            expected[size / 2] = 'x';
            assert(first.f_pos == size / 2 + 1);
            prepare_crc(h, expected, size, attrs);
            /* Reselection and repeated preparation must retain the write. */
            assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, h));
            prepare_crc(h, expected, size, attrs);
            assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, h));
        }
    }
}
static void initialization_failures(void)
{
    unsigned int mem_live, pages_live;
    reset();
    mem_live = mem_allocations - mem_frees;
    pages_live = page_allocations - page_frees;
    for (int type = B_TYPE_PLAIN; type <= B_TYPE_SCATTERED; ++type) {
        for (int failure = 0; failure < (type == B_TYPE_PLAIN ? 2 : 1); ++failure) {
            fail_mem_after = failure;
            assert(alloc(type, CHUNK_SIZE + 17, 0) == INVALID_BUFFER_HANDLE);
            fail_mem_after = -1;
            assert(mem_allocations - mem_frees == mem_live);
            assert(page_allocations - page_frees == pages_live);
        }
    }
    for (int failure = 0; failure < 3; ++failure) {
        fail_chunk_after = failure;
        assert(alloc(B_TYPE_SCATTERED, 2 * CHUNK_SIZE + 17, 0) == INVALID_BUFFER_HANDLE);
        fail_chunk_after = -1;
        assert(mem_allocations - mem_frees == mem_live);
        assert(page_allocations - page_frees == pages_live);
    }
    /* NAND retains its empty-stream CRC and has no payload to initialize. */
    for (int attrs = 0; attrs <= B_ATTR_VERIFY; ++attrs) {
        int h = alloc(B_TYPE_NAND, 123, attrs);
        uint32_t count, checksum = 0;
        assert(h >= 0);
        initialized_checksum(buffers.bufs[h].container.abstract, attrs);
        mutex_lock(&hbootctrl_mutex);
        get_bootlist(&count, INVALID_BUFFER_HANDLE);
        mutex_unlock(&hbootctrl_mutex);
        assert(count == 1);
        assert(buffers.bufs[h].container.abstract->checksum == checksum);
        assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, h));
    }
}

struct job { unsigned int cmd; unsigned long arg; int write, result; };
static void *worker(void *arg)
{
    struct job *job = arg;
    struct file f = { 0 };
    job->result = job->write ? hbootctrl_write(&f, "abcdefgh", 8, &f.f_pos) :
                             ioctl_op(&f, job->cmd, job->arg);
    pthread_mutex_lock(&monitor);
    ++completed;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&monitor);
    return NULL;
}
/* Pause one real operation and prove all contenders reach the shared mutex
 * without completing. No sleeps or scheduler-timing assumptions. */
static int race(int stage, struct job owner, struct job *others, int count)
{
    pthread_t threads[5];
    int i, baseline;
    pthread_mutex_lock(&monitor);
    pause_at = stage; paused = resume_op = completed = 0;
    pthread_mutex_unlock(&monitor);
    assert(!pthread_create(&threads[0], NULL, worker, &owner));
    pthread_mutex_lock(&monitor);
    while (!paused) pthread_cond_wait(&changed, &monitor);
    baseline = attempts;
    pthread_mutex_unlock(&monitor);
    for (i = 0; i < count; ++i)
        assert(!pthread_create(&threads[i+1], NULL, worker, &others[i]));
    pthread_mutex_lock(&monitor);
    while (attempts < baseline + count) pthread_cond_wait(&changed, &monitor);
    assert(completed == 0);
    resume_op = 1;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&monitor);
    for (i = 0; i <= count; ++i) assert(!pthread_join(threads[i], NULL));
    assert(completed == count + 1);
    return owner.result;
}
/* Snapshot live handles, allocations and payloads across every replacement. */
static void check_live(void **live, char payload[MAX_BUFFERS_COUNT][8])
{
    int i;
    mutex_lock(&hbootctrl_mutex);
    assert(buffers.used == MAX_BUFFERS_COUNT);
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i) {
        assert(buffers.bufs[i].container.generic == live[i]);
        if (live[i])
            assert(!memcmp(buffers.bufs[i].container.plain->data, payload[i], 8));
    }
    mutex_unlock(&hbootctrl_mutex);
}
static void replace_slot(int slot, void **live, char payload[MAX_BUFFERS_COUNT][8])
{
    assert(alloc(B_TYPE_PLAIN, 8, 0) == slot);
    assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, slot));
    first.f_pos = 0;
    assert(hbootctrl_write(&first, payload[slot], 8, &first.f_pos) == 8);
    assert(first.f_pos == 8);
    live[slot] = buffers.bufs[slot].container.generic;
    check_live(live, payload);
}
/* Issue #39: full-table rejection must precede every typed allocator. */
static void full_table_rejection(void **live, char payload[MAX_BUFFERS_COUNT][8])
{
    struct buffers_ctx before = buffers;
    struct plain_buffer metadata[MAX_BUFFERS_COUNT];
    unsigned int mem_before = mem_attempts, pages_before = page_attempts;
    unsigned int mem_freed = mem_frees, pages_freed = page_frees;
    int i, type, direct;
    first.f_pos = 3;
    second.f_pos = 7;
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i)
        memcpy(&metadata[i], buffers.bufs[i].container.plain, sizeof(metadata[i]));
    for (type = B_TYPE_PLAIN; type <= B_TYPE_NAND; ++type) {
        for (direct = 0; direct < 2; ++direct) {
            if (direct) {
                mutex_lock(&hbootctrl_mutex);
                assert(allocate_buffer(IMG_HBOOT, type, B_ATTR_VERIFY, CHUNK_SIZE + 17, 123)
                       == INVALID_BUFFER_HANDLE);
                mutex_unlock(&hbootctrl_mutex);
            } else assert(alloc(type, CHUNK_SIZE + 17, B_ATTR_VERIFY)
                          == INVALID_BUFFER_HANDLE);
            assert(mem_attempts == mem_before && page_attempts == pages_before);
            assert(mem_frees == mem_freed && page_frees == pages_freed);
            assert(!memcmp(&before, &buffers, sizeof(before)));
            assert(first.f_pos == 3 && second.f_pos == 7);
            check_live(live, payload);
            for (i = 0; i < MAX_BUFFERS_COUNT; ++i)
                assert(!memcmp(&metadata[i], buffers.bufs[i].container.plain,
                               sizeof(metadata[i])));
            assert(!pthread_mutex_trylock(&hbootctrl_mutex));
            pthread_mutex_unlock(&hbootctrl_mutex);
        }
    }
}
/* Incomplete allocation requests must not reach any typed allocator. */
static void allocation_copy_faults(void)
{
    struct plain_buffer plain;
    struct nand_buffer nand;
    unsigned char scattered[sizeof(struct scattered_buffer) + 2 * sizeof(uint32_t)];
    char payload[CHUNK_SIZE + 17], actual[sizeof(payload)];
    uint32_t bootlist[MAX_BUFFERS_COUNT];
    struct buffers_ctx before;
    unsigned int mem_before, pages_before, mem_freed, pages_freed;
    size_t copied;
    int type, caller;
    reset();
    assert(alloc(B_TYPE_PLAIN, sizeof(payload), B_ATTR_VERIFY) == 0);
    assert(alloc(B_TYPE_SCATTERED, sizeof(payload), B_ATTR_VERIFY) == 1);
    assert(alloc(B_TYPE_NAND, sizeof(payload), B_ATTR_VERIFY) == 2);
    memset(payload, 0x6b, sizeof(payload));
    for (type = 0; type < 2; ++type) {
        assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, type));
        assert(hbootctrl_write(&first, payload, sizeof(payload), &first.f_pos)
               == sizeof(payload));
    }
    first.f_pos = 3;
    second.f_pos = 7;
    before = buffers;
    memcpy(&plain, buffers.bufs[0].container.plain, sizeof(plain));
    memcpy(scattered, buffers.bufs[1].container.scattered, sizeof(scattered));
    memcpy(&nand, buffers.bufs[2].container.nand, sizeof(nand));
    memcpy(bootlist, buffers.bootlist, sizeof(bootlist));
    mem_before = mem_attempts; pages_before = page_attempts;
    mem_freed = mem_frees; pages_freed = page_frees;
    for (type = B_TYPE_PLAIN; type <= B_TYPE_NAND; ++type) {
        struct hboot_buffer_req req = {
            IMG_LINUX, type, B_ATTR_VERIFY, sizeof(payload), 123
        };
        for (caller = 0; caller < 2; ++caller) {
            struct file *file = caller ? &second : &first;
            for (copied = 0; copied < sizeof(req); ++copied) {
                assert(buffers.used < MAX_BUFFERS_COUNT);
                copy_budget = copied;
                assert(ioctl_op(file, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req)
                       == -EFAULT);
                assert(copy_budget == 0);
                assert(mem_attempts == mem_before && page_attempts == pages_before);
                assert(mem_frees == mem_freed && page_frees == pages_freed);
                assert(!memcmp(&before, &buffers, sizeof(before)));
                assert(!memcmp(bootlist, buffers.bootlist, sizeof(bootlist)));
                assert(first.f_pos == 3 && second.f_pos == 7);
                assert(!memcmp(&plain, buffers.bufs[0].container.plain, sizeof(plain)));
                assert(!memcmp(scattered, buffers.bufs[1].container.scattered,
                               sizeof(scattered)));
                assert(!memcmp(&nand, buffers.bufs[2].container.nand, sizeof(nand)));
                for (int h = 0; h < 2; ++h) {
                    snapshot_payload(h, actual, sizeof(actual));
                    assert(!memcmp(payload, actual, sizeof(payload)));
                }
                assert(!pthread_mutex_trylock(&hbootctrl_mutex));
                pthread_mutex_unlock(&hbootctrl_mutex);
            }
        }
        copy_budget = (size_t)-1;
        assert(ioctl_op(&second, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req) == 3);
        assert(buffers.bufs[3].container.abstract->type == type);
        assert(!ioctl_op(&second, HBOOT_FREE_BUFFER, 3));
        /* Freeing the successful request preserves the high-water extent. */
        before = buffers;
        mem_before = mem_attempts; pages_before = page_attempts;
        mem_freed = mem_frees; pages_freed = page_frees;
    }
    /* A fully copied unsupported type retains the allocation error value. */
    assert(alloc(B_TYPE_NAND + 1, sizeof(payload), B_ATTR_VERIFY)
           == INVALID_BUFFER_HANDLE);
}
/* Issue #41: unsupported tags must fail with capacity still available. */
static void image_tag_validation(void)
{
    const uint8_t unsupported[] = { IMG_LAST_TAG + 1, 255 };
    struct plain_buffer plain;
    struct nand_buffer nand;
    unsigned char scattered[sizeof(struct scattered_buffer) + 2 * sizeof(uint32_t)];
    char payload[CHUNK_SIZE + 17], actual[sizeof(payload)];
    int type, direct, tag;
    unsigned int i;
    reset();
    assert(alloc(B_TYPE_PLAIN, sizeof(payload), B_ATTR_VERIFY) == 0);
    assert(alloc(B_TYPE_SCATTERED, sizeof(payload), B_ATTR_VERIFY) == 1);
    assert(alloc(B_TYPE_NAND, sizeof(payload), B_ATTR_VERIFY) == 2);
    memset(payload, 0x6b, sizeof(payload));
    for (type = 0; type < 2; ++type) {
        assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, type));
        assert(hbootctrl_write(&first, payload, sizeof(payload), &first.f_pos)
               == sizeof(payload));
    }
    first.f_pos = 3;
    second.f_pos = 7;
    memcpy(&plain, buffers.bufs[0].container.plain, sizeof(plain));
    memcpy(scattered, buffers.bufs[1].container.scattered, sizeof(scattered));
    memcpy(&nand, buffers.bufs[2].container.nand, sizeof(nand));
    for (type = B_TYPE_PLAIN; type <= B_TYPE_NAND; ++type) {
        for (direct = 0; direct < 2; ++direct) {
            for (i = 0; i < sizeof(unsupported) / sizeof(unsupported[0]); ++i) {
                struct hboot_buffer_req req = {
                    unsupported[i], type, B_ATTR_VERIFY, sizeof(payload), 123
                };
                struct buffers_ctx before = buffers;
                unsigned int mem_before = mem_attempts, pages_before = page_attempts;
                unsigned int mem_freed = mem_frees, pages_freed = page_frees;
                assert(buffers.used < MAX_BUFFERS_COUNT);
                if (direct) {
                    mutex_lock(&hbootctrl_mutex);
                    assert(allocate_buffer(req.tag, req.type, req.attrs, req.size, req.rest)
                           == INVALID_BUFFER_HANDLE);
                    mutex_unlock(&hbootctrl_mutex);
                } else {
                    assert(ioctl_op(&second, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req)
                           == INVALID_BUFFER_HANDLE);
                }
                assert(mem_attempts == mem_before && page_attempts == pages_before);
                assert(mem_frees == mem_freed && page_frees == pages_freed);
                assert(!memcmp(&before, &buffers, sizeof(before)));
                assert(first.f_pos == 3 && second.f_pos == 7);
                assert(!memcmp(&plain, buffers.bufs[0].container.plain, sizeof(plain)));
                assert(!memcmp(scattered, buffers.bufs[1].container.scattered,
                               sizeof(scattered)));
                assert(!memcmp(&nand, buffers.bufs[2].container.nand, sizeof(nand)));
                for (int h = 0; h < 2; ++h) {
                    snapshot_payload(h, actual, sizeof(actual));
                    assert(!memcmp(payload, actual, sizeof(payload)));
                }
                assert(!pthread_mutex_trylock(&hbootctrl_mutex));
                pthread_mutex_unlock(&hbootctrl_mutex);
                /* Every supported tag, including duplicate IMG_HBOOT, remains
                 * valid for every type through both entry paths after rejection. */
                for (tag = IMG_HBOOT; tag <= IMG_LAST_TAG; ++tag) {
                    int handle;
                    req.tag = tag;
                    if (direct) {
                        mutex_lock(&hbootctrl_mutex);
                        handle = allocate_buffer(req.tag, req.type, req.attrs,
                                                 req.size, req.rest);
                        mutex_unlock(&hbootctrl_mutex);
                    } else {
                        handle = ioctl_op(&second, HBOOT_ALLOCATE_BUFFER,
                                          (unsigned long)&req);
                    }
                    assert(handle == 3);
                    assert(buffers.bufs[handle].container.abstract->tag == tag);
                    assert(buffers.bufs[handle].container.abstract->type == type);
                    assert(!ioctl_op(&second, HBOOT_FREE_BUFFER, handle));
                }
            }
        }
    }
}
static void slot_reuse(void)
{
    void *live[MAX_BUFFERS_COUNT];
    char payload[MAX_BUFFERS_COUNT][8];
    int i, cycle, middle = MAX_BUFFERS_COUNT / 2;
    struct hboot_buffer_req req = { 0, B_TYPE_PLAIN, 0, 8, 0 };
    struct job allocation = { HBOOT_ALLOCATE_BUFFER, (unsigned long)&req, 0, 0 };
    struct job other = allocation;
    reset();
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i) {
        memset(payload[i], 'a' + i, 8);
        assert(alloc(B_TYPE_PLAIN, 8, 0) == i);
        assert(!ioctl_op(&first, HBOOT_SELECT_BUFFER, i));
        first.f_pos = 0;
        assert(hbootctrl_write(&first, payload[i], 8, &first.f_pos) == 8);
        live[i] = buffers.bufs[i].container.generic;
    }
    full_table_rejection(live, payload);
    check_live(live, payload);
    /* Full extent, with the last slot still live. */
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, 0)); live[0] = NULL;
    replace_slot(0, live, payload);
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, middle)); live[middle] = NULL;
    /* A failed allocation must leave the available hole unpublished. */
    for (int type = B_TYPE_PLAIN; type <= B_TYPE_NAND; ++type) {
        struct buffers_ctx before = buffers;
        unsigned int attempted = mem_attempts;
        fail_mem_after = 0;
        assert(alloc(type, 8, 0) == INVALID_BUFFER_HANDLE);
        fail_mem_after = -1;
        assert(mem_attempts == attempted + 1);
        assert(!memcmp(&before, &buffers, sizeof(before)));
        check_live(live, payload);
    }
    replace_slot(middle, live, payload);
    /* Last-slot preference, followed by deterministic earlier-hole reuse. */
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, 0)); live[0] = NULL;
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, middle)); live[middle] = NULL;
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, MAX_BUFFERS_COUNT - 1));
    live[MAX_BUFFERS_COUNT - 1] = NULL;
    replace_slot(MAX_BUFFERS_COUNT - 1, live, payload);
    replace_slot(0, live, payload);
    replace_slot(middle, live, payload);
    /* No reset: refill an entirely freed table at its existing extent. */
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i) {
        assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, i)); live[i] = NULL;
    }
    replace_slot(MAX_BUFFERS_COUNT - 1, live, payload);
    for (i = 0; i < MAX_BUFFERS_COUNT - 1; ++i) replace_slot(i, live, payload);
    for (cycle = 0; cycle < MAX_BUFFERS_COUNT * 3; ++cycle) {
        i = cycle % MAX_BUFFERS_COUNT;
        assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, i)); live[i] = NULL;
        replace_slot(i, live, payload);
    }
    /* Both requests reach the operation mutex; only the owner gets the hole. */
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, middle)); live[middle] = NULL;
    {
        unsigned int mem_before = mem_attempts, pages_before = page_attempts;
        assert(race(1, allocation, &other, 1) == middle);
        assert(mem_attempts == mem_before + 2 && page_attempts == pages_before);
    }
    assert(other.result == INVALID_BUFFER_HANDLE);
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, middle));
    replace_slot(middle, live, payload);
    /* The mocked handoff must include the replacement once and omit holes. */
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, 0)); live[0] = NULL;
    replace_slot(0, live, payload);
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, 1)); live[1] = NULL;
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, middle)); live[middle] = NULL;
    check_live(live, payload);
    memcpy(reuse_snapshot, live, sizeof(live));
    reuse_boot_handle = MAX_BUFFERS_COUNT - 1;
    verify_reuse = 1;
    assert(ioctl_op(&first, HBOOT_BOOT, reuse_boot_handle) == -EBUSY);
    assert(!verify_reuse);
    check_live(live, payload);
}
int main(void)
{
    int i, stage, handles[MAX_BUFFERS_COUNT];
    const int boot_stages[] = { 1, 3, 2, 4, 5, 6, 7 };
    struct hboot_buffer_req req = { 0, B_TYPE_PLAIN, 0, 8, 0 };
    struct job writer = { 0, 0, 1, 0 }, boot = { HBOOT_BOOT, 0, 0, 0 };
    struct job contenders[4] = {
        { HBOOT_FREE_BUFFER, 1, 0, 0 }, { 0, 0, 1, 0 },
        { HBOOT_ALLOCATE_BUFFER, (unsigned long)&req, 0, 0 },
        { HBOOT_BOOT, 0, 0, 0 }
    };
    assert(sizeof(void *) == 4);
    assert(!buffers_init());
    boot_buffer_preflight();
    uart_rates();
    uart_polling();
    uart_routing_errors();
    display_errors();
    selection(B_TYPE_PLAIN); selection(B_TYPE_SCATTERED);
    writes(B_TYPE_PLAIN); writes(B_TYPE_SCATTERED);
    for (i = 0; i < 2; ++i) {
        initialization(B_TYPE_PLAIN, i ? B_ATTR_VERIFY : 0);
        initialization(B_TYPE_SCATTERED, i ? B_ATTR_VERIFY : 0);
        crc_lifecycle(B_TYPE_PLAIN, i ? B_ATTR_VERIFY : 0);
        crc_lifecycle(B_TYPE_SCATTERED, i ? B_ATTR_VERIFY : 0);
    }
    initialization_failures();
    allocation_copy_faults();
    image_tag_validation();
    slot_reuse();
    reset();
    assert(ioctl_op(&first, HBOOT_FREE_BUFFER, -1) == -1);
    assert(ioctl_op(&first, HBOOT_FREE_BUFFER, MAX_BUFFERS_COUNT) == -1);
    assert(ioctl_op(&first, HBOOT_FREE_BUFFER, 0) == -1);
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i) handles[i] = alloc(B_TYPE_PLAIN, 8, 0);
    for (i = 0; i < MAX_BUFFERS_COUNT; ++i) assert(handles[i] == i);
    assert(alloc(B_TYPE_PLAIN, 8, 0) == -1);
    assert(!ioctl_op(&first, HBOOT_FREE_BUFFER, MAX_BUFFERS_COUNT-1));
    /* Two allocations competing for the reusable last slot: one succeeds. */
    {
        struct job allocation = contenders[2], other = contenders[2];
        assert(race(1, allocation, &other, 1) == MAX_BUFFERS_COUNT - 1);
        assert(other.result == -1);
    }
    for (int checkpoint_index = 0; checkpoint_index < 7; ++checkpoint_index) {
        stage = boot_stages[checkpoint_index];
        reset();
        assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
        assert(alloc(B_TYPE_PLAIN, 8, B_ATTR_VERIFY) == 1);
        assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, 1));
        assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == 8);
        expected_crc = crc32((const uint8_t *)"abcdefgh", 8);
        /* Payload snapshot applies to the paused owner; every transition
         * checks published CRCs against current contents above. */
        verify_snapshot = stage != 1;
        if (stage == 1) {
            assert(race(stage, writer, contenders, 1) == 8);
            assert(contenders[0].result == 0);
            assert(buffers.handle == INVALID_BUFFER_HANDLE);
            assert(hbootctrl_write(&second, "abcdefgh", 8, &second.f_pos) == -EINVAL);
            assert(second.f_pos == 0);
        } else race(stage, boot, contenders, 4);
    }
    reset();
    assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
    assert(alloc(B_TYPE_PLAIN, 8, B_ATTR_VERIFY) == 1);
    ioctl_op(&first, HBOOT_SELECT_BUFFER, 1);
    assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == 8);
    verify_snapshot = 1;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EBUSY);
    verify_snapshot = 0;
    /* Every preparation error must leave the mutex available. */
    fail_pages = 1;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -ENOMEM);
    fail_pages = 0;
    misalign_pages = 1;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -EINVAL);
    misalign_pages = 0;
    assert(ioctl_op(&first, HBOOT_BOOT, MAX_BUFFERS_COUNT) == -EINVAL);
    fail_list = 1;
    assert(ioctl_op(&first, HBOOT_BOOT, 0) == -ENOMEM);
    fail_list = 0;
    copy_budget = 0;
    assert(ioctl_op(&first, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req) == -EFAULT);
    copy_budget = (size_t)-1;
    assert(ioctl_op(&first, 999, 0) == -EINVAL);
    assert(!pthread_mutex_trylock(&hbootctrl_mutex));
    pthread_mutex_unlock(&hbootctrl_mutex);
    reset(); buffers_destroy();
    puts("hbootmod buffer and operation-lock checks passed");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='hbootmod-locking-') as directory:
    test_source = Path(directory) / 'locking.c'
    executable = Path(directory) / 'locking'
    for verify in (True, False):
        configuration = '#define HBOOT_VERIFY_CRC32\n' if verify else ''
        test_source.write_text(configuration + preamble + uart + '\n' + header + crc + buffers + '\n' + mutex +
                               '\n' + mock + boot + '\n' + control + tests)
        subprocess.run([os.environ.get('CC', 'cc'), '-m32', '-std=gnu99', '-pthread',
                        '-Wall', '-Wextra', '-Wno-unused-parameter',
                        str(test_source), '-o', str(executable)], check=True, timeout=60)
        subprocess.run([str(executable)], check=True, timeout=30)
