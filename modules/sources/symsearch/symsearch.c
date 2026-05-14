/*
 * symsearch: - looks up also for unexproted symbols in the kernel
 *
 * exports function:
 * unsigned long lookup_symbol_address(const char *name);
 *
 * Created by Skrilax_CZ
 * GPL
 *
 * Copyright (C) 2010 Skrilax_CZ
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/string.h>
#include "symsearch.h"

/* 
 * We use kallsyms_on_each_symbol (which is exported by the kernel)
 * to find the address of kallsyms_lookup_name (which is NOT exported).
 */
extern int kallsyms_on_each_symbol(int (*fn)(void *, const char *, struct module *,
			unsigned long), void *data);

// Define the function pointer and export it
unsigned long (*lookup_symbol_address)(const char *name) = NULL;
EXPORT_SYMBOL(lookup_symbol_address);

static int find_kallsyms_lookup_name(void* data, const char* name,
			struct module * module, unsigned long address)
{
	if (!strcmp(name, "kallsyms_lookup_name"))
	{
		printk(KERN_INFO "symsearch: found kallsyms_lookup_name at 0x%lx.\n", address);
		lookup_symbol_address = (void *)address;
		return 1; // Stop searching
	}
	return 0;
}

static int __init symsearch_init(void)
{
	kallsyms_on_each_symbol(&find_kallsyms_lookup_name, NULL);
    
	if(!lookup_symbol_address)
	{
		printk(KERN_ERR "symsearch: CRITICAL - could not find kallsyms_lookup_name.\n");
		return -ENODEV;
	}
	return 0;
}

static void __exit symsearch_exit(void)
{
	printk(KERN_INFO "symsearch: unloaded.\n");
}

module_init(symsearch_init);
module_exit(symsearch_exit);

MODULE_VERSION("1.2");
MODULE_AUTHOR("Skrilax_CZ, palmbeach05");
MODULE_DESCRIPTION("Helper to find unexported kernel symbols");
MODULE_LICENSE("GPL");
