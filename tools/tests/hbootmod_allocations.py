#!/usr/bin/env python3
"""Run on a suitable development host, not the inspection sandbox.

Uses mocked allocators against the allocation helper extracted from buffers.c.
Run: python3 tools/tests/hbootmod_allocations.py
This does not validate target-kernel compilation, allocator behavior, or boot.
"""
from pathlib import Path
import os
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] /
          'modules/sources/hbootmod/buffers.c').read_text()
helper = source[source.index('#define HIGH_ALLOC_ATTEMPTS'):
                source.index('void free_high_pages(')]
preamble = r'''
#include <assert.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef unsigned long uint32_t;
#define PAGE_SIZE 4096UL
#define GFP_KERNEL 0
struct allocation { unsigned long address; unsigned int order; int pages, freed; };
static struct allocation allocations[1024];
static unsigned int used, calls, succeed_at, fail_at, bookkeeping_calls;
static int want_bookkeeping, fail_bookkeeping;
static void *bookkeeping;
static unsigned int get_order(size_t size)
{
    unsigned int order = 0;
    size_t bytes = PAGE_SIZE;
    while (bytes < size) { bytes <<= 1; ++order; }
    return order;
}
static unsigned long allocate(int pages, unsigned int order)
{
    struct allocation *a;
    ++calls;
    if (calls == fail_at) return 0;
    assert(used < 1024);
    a = &allocations[used++];
    a->address = (calls == succeed_at ? 0x90000000UL : 0x80000000UL)
                 + used * 0x10000UL;
    a->pages = pages;
    a->order = order;
    a->freed = 0;
    return a->address;
}
static int good_address(unsigned long address)
{
    if (address >= 0x88c00000UL) return 1;
    want_bookkeeping = bookkeeping == NULL;
    return 0;
}
#define GOOD_ADDRESS(p) good_address(p)
static void *kmalloc(size_t size, int flags)
{
    (void)flags;
    if (want_bookkeeping) {
        want_bookkeeping = 0;
        ++bookkeeping_calls;
        if (fail_bookkeeping) return NULL;
        bookkeeping = malloc(size);
        assert(bookkeeping);
        memset(bookkeeping, 0xa5, size);
        return bookkeeping;
    }
    return (void *)allocate(0, get_order(size));
}
static unsigned long __get_free_pages(int flags, unsigned int order)
{
    (void)flags;
    return allocate(1, order);
}
static void release(unsigned long address, int pages, unsigned int order)
{
    unsigned int i;
    for (i = 0; i < used; ++i) {
        struct allocation *a = &allocations[i];
        if (a->address != address) continue;
        assert(!a->freed && a->pages == pages);
        if (pages) assert(a->order == order);
        a->freed = 1;
        return;
    }
    assert(0 && "unknown allocation");
}
static void kfree(void *p)
{
    if (!p) return;
    if (p == bookkeeping) { free(p); bookkeeping = NULL; return; }
    release((unsigned long)p, 0, 0);
}
static void free_pages(unsigned long p, unsigned int order)
{
    release(p, 1, order);
}
'''
tests = r'''
static void scenario(int pages, unsigned int order, size_t size,
                     unsigned int success, unsigned int failure, int book_failure,
                     unsigned int expected_calls, int expected_success)
{
    unsigned int i;
    unsigned long result;
    assert(bookkeeping == NULL);
    used = calls = bookkeeping_calls = 0;
    want_bookkeeping = 0;
    succeed_at = success;
    fail_at = failure;
    fail_bookkeeping = book_failure;
    result = pages ? get_high_pages(order) : get_high_mem(size);
    assert(calls == expected_calls);
    assert(!!result == expected_success);
    assert(bookkeeping == NULL);
    assert(bookkeeping_calls <= 1);
    for (i = 0; i < used; ++i)
        assert(allocations[i].freed == (allocations[i].address != result));
    if (result) {
        if (pages) free_pages(result, order);
        else kfree((void *)result);
    }
    for (i = 0; i < used; ++i) assert(allocations[i].freed);
}
int main(void)
{
    unsigned int repeat, order;
    for (repeat = 0; repeat < 100; ++repeat) {
        for (order = 0; order <= 2; order += 2) {
            scenario(1, order, 0, 1, 0, 0, 1, 1);
            scenario(1, order, 0, 5, 0, 0, 5, 1);
            scenario(1, order, 0, 0, 4, 0, 4, 0);
            scenario(1, order, 0, 0, 0, 0, 128, 0);
            scenario(1, order, 0, 0, 0, 1, 1, 0);
        }
        scenario(0, 0, 32, 1, 0, 0, 1, 1);
        scenario(0, 0, 32, 5, 0, 0, 5, 1);
        scenario(0, 0, 32, 0, 4, 0, 4, 0);
        scenario(0, 0, 32, 0, 0, 0, 128, 0);
        scenario(0, 0, 32, 0, 0, 1, 1, 0);
        scenario(0, 0, 0, 0, 0, 0, 0, 0);
        /* Byte limit, including conservative rounding of kmalloc sizes. */
        scenario(0, 0, 1024 * 1024, 0, 0, 0, 8, 0);
        scenario(0, 0, 1024 * 1024 + 1, 0, 0, 0, 4, 0);
        scenario(1, 8, 0, 0, 0, 0, 8, 0);
        scenario(0, 0, HIGH_ALLOC_BYTES, 1, 0, 0, 1, 1);
        scenario(0, 0, HIGH_ALLOC_BYTES + 1, 0, 0, 0, 0, 0);
        scenario(1, 12, 0, 0, 0, 0, 0, 0);
    }
    puts("hbootmod allocation ownership checks passed");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='hbootmod-allocations-') as directory:
    test_source = Path(directory) / 'allocations.c'
    executable = Path(directory) / 'allocations'
    test_source.write_text(preamble + helper + tests)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu89', '-Wall', '-Wextra',
                    '-Werror', str(test_source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
