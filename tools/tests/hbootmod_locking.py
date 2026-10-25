#!/usr/bin/env python3
"""Host-only regression harness; do not run in the inspection sandbox.

Run: python3 tools/tests/hbootmod_locking.py
Requires a Linux development host with a 32-bit C library/compiler (-m32) and
pthreads, matching the source's 32-bit pointer storage. Uses actual buffer,
CRC, ioctl, write and boot-preparation code; mocks allocation, user copies,
UART/display and the irreversible transition. Does not validate kernel locking,
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
    start = re.search(re.escape(signature.rstrip()) + r'[^\S\n]*\n\{', text).start()
    end = text.index('\n}', start) + 2
    return text[start:end]


buffers = without_includes((source / 'buffers.c').read_text())
start = buffers.index('/*\n * The device exposes')
end = buffers.index('static void init_abstract_buffer', start)
buffers = buffers[:start] + buffers[end:]
hboot = (source / 'hboot.c').read_text()
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
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/types.h>
#define __user
#define HBOOT_VERIFY_CRC32
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
    if (copy_budget != (size_t)-1) copy_budget -= copied;
    return size - copied;
}
static int fail_pages, misalign_pages, fail_list, emu_uart = 1, kill_dss = 1;
static uint32_t get_high_mem(size_t size)
{
    void *p = calloc(1, size);
    assert(p);
    return (uint32_t)p;
}
static void free_high_mem(void *p) { free(p); }
static uint32_t get_high_pages(unsigned int order)
{
    void *p;
    checkpoint(2);
    if (fail_pages) return 0;
    assert(!posix_memalign(&p, 16384, PAGE_SIZE << order));
    memset(p, 0, PAGE_SIZE << order);
    return (uint32_t)p + (misalign_pages ? 4 : 0);
}
static void free_high_pages(void *p, unsigned int order) { (void)order; free((char *)p - (misalign_pages ? 4 : 0)); }
static void build_l1_table(uint32_t *table) { (void)table; }
static void activate_emu_uart(void) { checkpoint(5); }
static void reconfigure_emu_uart(int speed) { (void)speed; }
static void disable_dss(void) { checkpoint(6); }
'''
# Headers supply the real ABI and declarations; allocator mocks above are static.
header = without_includes((source / 'buffers.h').read_text())
header += without_includes((source / 'hboot.h').read_text())
header = re.sub(r'^(?:uint32_t|void) (?:get_high_\w+|free_high_\w+)\([^;]+;\n', '', header, flags=re.MULTILINE)
crc = without_includes((source / 'crc32.c').read_text())
mock = r'''
static uint32_t expected_crc;
static int verify_snapshot;
static void mock_transition(void *list, uint32_t count, bootfunc_t entry)
{
    checkpoint(7);
    assert(entry && list);
    if (verify_snapshot) {
        struct abstract_buffer *a;
        assert(count == 1);
        a = (void *)((uint32_t *)list)[0];
        assert(a->checksum == expected_crc && a->state == B_STAT_CREATED);
        assert(!memcmp(buffers.bufs[1].container.plain->data, "abcdefgh", 8));
        verify_snapshot = 0;
    }
}
'''
tests = r'''
static struct file first, second;
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
        assert(buffers.bufs[h].container.abstract->checksum ==
               (crc32((const uint8_t *)data, limit) ^ 0xffffffff));
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
static void race(int stage, struct job owner, struct job *others, int count)
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
}
int main(void)
{
    int i, stage, handles[MAX_BUFFERS_COUNT];
    struct hboot_buffer_req req = { 0, B_TYPE_PLAIN, 0, 8, 0 };
    struct job writer = { 0, 0, 1, 0 }, boot = { HBOOT_BOOT, 0, 0, 0 };
    struct job contenders[4] = {
        { HBOOT_FREE_BUFFER, 1, 0, 0 }, { 0, 0, 1, 0 },
        { HBOOT_ALLOCATE_BUFFER, (unsigned long)&req, 0, 0 },
        { HBOOT_BOOT, 0, 0, 0 }
    };
    assert(sizeof(void *) == 4);
    assert(!buffers_init());
    writes(B_TYPE_PLAIN); writes(B_TYPE_SCATTERED);
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
        race(1, allocation, &other, 1);
        assert(other.result == -1);
    }
    for (stage = 1; stage <= 7; ++stage) {
        reset();
        assert(alloc(B_TYPE_PLAIN, 8, 0) == 0);
        assert(alloc(B_TYPE_PLAIN, 8, B_ATTR_VERIFY) == 1);
        assert(!ioctl_op(&second, HBOOT_SELECT_BUFFER, 1));
        assert(hbootctrl_write(&first, "abcdefgh", 8, &first.f_pos) == 8);
        expected_crc = crc32((const uint8_t *)"abcdefgh", 8);
        /* Snapshot verification is only for the paused boot, before contenders
         * run. A subsequent boot intentionally retains existing CRC semantics. */
        verify_snapshot = stage != 1;
        if (stage == 1) race(stage, writer, contenders, 1);
        else race(stage, boot, contenders, 4);
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
    assert(ioctl_op(&first, HBOOT_ALLOCATE_BUFFER, (unsigned long)&req) == -EINVAL);
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
    test_source.write_text(preamble + header + crc + buffers + '\n' + mutex +
                           '\n' + mock + boot + '\n' + control + tests)
    subprocess.run([os.environ.get('CC', 'cc'), '-m32', '-std=gnu99', '-pthread',
                    '-Wall', '-Wextra', '-Wno-unused-parameter',
                    str(test_source), '-o', str(executable)], check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=30)
