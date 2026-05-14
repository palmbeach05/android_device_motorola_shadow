/*
 * hook - Hook utilities.
 * use of Skrilax's symsearch added by Nadlabak
 *
 * Copyright (C) 2010 Nothize
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

#include "hook.h"
#include "../symsearch/symsearch.h"
#include <linux/module.h>
#include <linux/kallsyms.h>
#include <linux/stop_machine.h>
#include <asm/cacheflush.h>

#define MODULE_NAME "backlight"
#define MODULE_TAG backlight

#ifdef DEBUG_HOOK
#define P(format, ...) printk(KERN_INFO "hook: " format, ## __VA_ARGS__)
#else
#define P(format, ...)
#endif

#define INFO(format, ...) (printk(KERN_INFO MODULE_NAME ": " format, ## __VA_ARGS__))

SYMSEARCH_DECLARE_FUNCTION_STATIC(unsigned long, pkallsyms_lookup_name, const char *);
SYMSEARCH_DECLARE_FUNCTION_STATIC(const char *, pkallsyms_lookup, unsigned long, unsigned long *, unsigned long *, char **, char *);

/* 
 * ARM Instruction Patching 
 */
int hook(struct hook_info *hi) {
	char targetName[KSYM_NAME_LEN];
	char *ptargetName;

	if (!hi->target) {
		if (hi->targetName) {
			hi->target = (unsigned int*)pkallsyms_lookup_name(hi->targetName);
		}
			if (!hi->target) {
				P("Target address not found for %s\n", hi->targetName ? hi->targetName : "NULL");
			return -1;
		}
		ptargetName = hi->targetName;
	} else {
		pkallsyms_lookup((unsigned int)hi->target, NULL, NULL, NULL, targetName);
		ptargetName = targetName;
	}

	P("target = %p(%s), newf = %x\n", hi->target, ptargetName, hi->newfunc);
    
	// Save the original instruction
	hi->asm0 = hi->target[0];

	/* 
	 * Use 1 instruction static replacement (Branch instruction)
	 * We calculate the relative offset for the ARM 'B' instruction.
	 */
	hi->target[0] = 0xea000000 + (0xffffff & (hi->newfunc - ((unsigned int)hi->target + 8)) / 4);

	/*
	 * CRITICAL: Flush the Instruction Cache.
	 * Data was written to the D-Cache, but the CPU executes from the I-Cache.
	 * Without this, the CPU might execute the old instructions.
	 */
	flush_icache_range((unsigned long)hi->target, (unsigned long)hi->target + 4);

	// Setup jump table for the original function continuation
	hi->jmp = 0xe51ff004; // LDR PC, [PC, #-4]
	hi->target_cont = hi->target + 1;

	INFO("hooked %s at %p\n", ptargetName, hi->target);
	return 0;
}

int unhook(struct hook_info *hi) {
	if (hi->target) {
		hi->target[0] = hi->asm0;
		// Flush again after restoring original code
		flush_icache_range((unsigned long)hi->target, (unsigned long)hi->target + 4);
		INFO("unhooked %p\n", hi->target);
	}
	return 0;
}

/*
 * Use stop_machine or preemption disabling instead of the old BKL (lock_kernel)
 */
int hook_init(void) {
	int i;
	SYMSEARCH_BIND_FUNCTION_TO(backlight, kallsyms_lookup_name, pkallsyms_lookup_name);
	SYMSEARCH_BIND_FUNCTION_TO(backlight, kallsyms_lookup, pkallsyms_lookup);

	if (!pkallsyms_lookup_name || !pkallsyms_lookup) {
		printk(KERN_ERR MODULE_NAME ": Symsearch failed to bind kallsyms functions!\n");
		return -ENODEV;
	}

	// Disable preemption to ensure atomic patching
	preempt_disable();
	for (i = 0; g_hi[i].newfunc; ++i) {
		hook(&g_hi[i]);
	}
	preempt_enable();
    
	return 0;
}

void hook_exit(void) {
	int i;
	preempt_disable();
	for (i = 0; g_hi[i].newfunc; ++i) {
		unhook(&g_hi[i]);
	}
	preempt_enable();
}
