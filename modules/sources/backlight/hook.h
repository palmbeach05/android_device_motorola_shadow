/*
 * hook - Hook utilities.
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

#ifndef _HOOK_H_
#define _HOOK_H_

#include <linux/types.h>

struct hook_info {
	/* 
	 * asm0 and jmp MUST stay at the top and stay together.
	 * This creates a tiny "trampoline" in memory.
	 */
	unsigned int asm0;         /* The original instruction we moved */
	unsigned int jmp;          /* The jump instruction (LDR PC...) */
	unsigned int *target_cont; /* Address of the 2nd instruction in original func */
    
	/* Metadata and addresses */
	unsigned int *target;      /* The function we are hijacking */
	char *targetName;          /* The name for kallsyms lookup */
	unsigned int newfunc;      /* Our replacement function */
};

/* 
 * Standard function prototypes 
 */
int hook(struct hook_info *hi);
int unhook(struct hook_info *hi);
int hook_init(void);
void hook_exit(void);

extern struct hook_info g_hi[];

/**
 * HOOK_INVOKE
 * Instead of relying on a counter, we cast the address of g_hi directly.
 * Since cpcap_regacc_write is usually the first (and only) entry in your 
 * array for this module, g_hi[0] is the safest bet.
 */
#define HOOK_INVOKE(_f, ...) ((typeof(&_f))&g_hi[0].asm0)(__VA_ARGS__)

/* 
 * Array Initializers 
 */
#define HOOK_INIT(f) { .targetName = #f, .newfunc = (unsigned int)f }
#define HOOK_INIT_END { .target = NULL, .newfunc = 0 }

#endif /* _HOOK_H_ */
