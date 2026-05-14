/*
 * symsearch: - looks up also for unexproted symbols in the kernel
 *
 * Copyright (C) 2010 Skrilax_CZ
 * GPL
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

#ifndef _SYMSEARCH_H_
#define _SYMSEARCH_H_

#include <linux/types.h>
#include <linux/errno.h>

// Function pointer type for the lookup engine
typedef unsigned long (*lookup_symbol_address_fp)(const char *name);

// Declare the lookup function as an extern (exported by symsearch.ko)
extern lookup_symbol_address_fp lookup_symbol_address;

/* --- ADDRESS MACROS --- */

#define SYMSEARCH_DECLARE_ADDRESS(name) \
	extern unsigned long name##_address

#define SYMSEARCH_DECLARE_ADDRESS_STATIC(name) \
	static unsigned long name##_address = 0

#define SYMSEARCH_INIT_ADDRESS(name) \
	unsigned long name##_address = 0

#define SYMSEARCH_GET_ADDRESS(name) \
	name##_address

/* --- FUNCTION MACROS --- */

#define SYMSEARCH_DECLARE_FUNCTION(ret, name, ...) \
	typedef ret (*name##_fp)(__VA_ARGS__); \
	extern name##_fp name

#define SYMSEARCH_DECLARE_FUNCTION_STATIC(ret, name, ...) \
	typedef ret (*name##_fp)(__VA_ARGS__); \
	static name##_fp name = 0

#define SYMSEARCH_INIT_FUNCTION(name) \
	name##_fp name = (name##_fp)0

/* --- BINDING MACROS --- */

/* 
 * NOTE: Using -ENODEV or -ENOENT is often more descriptive than -EBUSY 
 * for missing symbols in modern Android debugging.
 */

#define SYMSEARCH_BIND_FUNCTION_TO(module, name, sym) \
	if (lookup_symbol_address) { \
		sym = (sym##_fp)lookup_symbol_address(#name); \
	} \
	if (!sym) { \
		printk(KERN_ERR #module ": Could not find symbol: " #name "\n"); \
		return -ENODEV; \
	}

#define SYMSEARCH_BIND_FUNCTION_TO_NORET(module, name, sym) \
	if (lookup_symbol_address) { \
		sym = (sym##_fp)lookup_symbol_address(#name); \
	} \
	if (!sym) { \
		printk(KERN_ERR #module ": Could not find symbol: " #name "\n"); \
		return; \
	}

/* --- LEGACY HIJACKING STRUCTURE --- */
/* (Keeping this for compatibility, though we use hook_info now) */
struct hijack_info {
	unsigned long hijack_address;
	unsigned long redirection_address;
	unsigned long instruction_backup;
};

#endif /* _SYMSEARCH_H_ */
