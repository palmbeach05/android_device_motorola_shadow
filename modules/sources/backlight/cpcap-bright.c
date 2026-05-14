/*
 * backlight - Button backlight cpcap fix for Motorola Defy
 *
 * hooking taken from "n - for testing kernel function hooking" by Nothize
 * require symsearch module by Skrilaz
 *
 * Copyright (C) 2011 CyanogenDefy - GPL
 */

#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/proc_fs.h>
#include <linux/leds.h>
#include <linux/uaccess.h> // Cleaner for copy_from_user
#include <linux/spi/cpcap.h>

#include "hook.h"
#include "../symsearch/symsearch.h"

#define TAG "backlight"
#define CPCAP_BUTTON_DEV       "button-backlight"
#define CPCAP_BUTTON_BACKLIGHT CPCAP_REG_ADLC

// Simplified Mask Logic
#define CPCAP_BUTTON_WR_MASK_DEF     0x3FF
#define CPCAP_BUTTON_WR_MASK_PLUS    0x7FF

// module parameters
static short brightness = 4; // Default to 4 instead of -1
static short animate = 0;
static short defy_plus = 0;
static short log_enable = 0;
static short hook_enable = 0;

// internals
static short hooked = 0;
static struct proc_dir_entry *proc_root;
static struct led_classdev *button_dev = NULL;

unsigned short g_reg;
unsigned short g_mask_wr;
unsigned short g_last_value;

static char buf[32];

#define DBG(format, ...) if (log_enable) printk(KERN_DEBUG TAG ": " format, ## __VA_ARGS__)

/*
 * Improved Conversion: Cleaned up logic and bitwise operations
 */
unsigned short brightness_to_cpcap(unsigned short level) {
	unsigned short val, newval;

	if (level == 0) return 0;
    
	level &= 0xFF; // Clamp to 8-bit

	if (defy_plus) {
		// Optimized Defy+ Logic
		if (level < 8) {
			newval = level * 8;
		} else {
			newval = (level * 8) | ((level & 0xC0) / 0x20);
		}
		newval |= 0x1; // Set 'On' bit
	} else {
		// Standard Defy Logic
		newval = (level <= 5) ? 0x1F : (level * 4) | 0xF;
	}

	val = newval & g_mask_wr;
	DBG("convert %d -> 0x%x\n", level, val);
	return val;
}

SYMSEARCH_DECLARE_FUNCTION_STATIC(
	int, _cpcap_direct_misc_write, unsigned short reg, unsigned short value, unsigned short mask);

/*
 * Animation - Cleaned up to use local variables and avoid multiple binds
 */
int brightness_fading(short level) {
	unsigned short n, val;

	SYMSEARCH_BIND_FUNCTION_TO(backlight, cpcap_direct_misc_write, _cpcap_direct_misc_write);
	if (!_cpcap_direct_misc_write) return -ENODEV;

	for (n = 1; n < 32; n++) {
		val = brightness_to_cpcap(n * 8 - 1);
		_cpcap_direct_misc_write(g_reg, val, g_mask_wr);
		msleep_interruptible(3);
	}
	for (; n > 0; n--) {
		val = brightness_to_cpcap(n * 8 - 1);
		_cpcap_direct_misc_write(g_reg, val, g_mask_wr);
		msleep_interruptible(1);
	}

	_cpcap_direct_misc_write(g_reg, 0, g_mask_wr);
	return 0;
}

/*
 * Hooked function
 */
int cpcap_regacc_write(struct cpcap_device *cpcap, enum cpcap_reg reg, unsigned short value, unsigned short mask) {

	if (reg != CPCAP_BUTTON_BACKLIGHT)
		goto invoke;

	// Sync with Android LED system if possible
	if (button_dev && button_dev->brightness > 1) {
		brightness = button_dev->brightness;
	}

	value = brightness_to_cpcap(brightness);
	g_mask_wr |= mask;
	g_last_value = value;

	// Fix for Defy+ mask discrepancy
	if (defy_plus && mask == 0xf) {
		mask = g_mask_wr;
	}

	DBG("hook write REG 0x%02x val 0x%x mask %x\n", (unsigned int) reg, value, mask);

invoke:
	return HOOK_INVOKE(cpcap_regacc_write, cpcap, reg, value, mask);
}

/*
 * ProcFS functions - Fixed sscanf types and added safety checks
 */
static int proc_brightness_read(char *buffer, char **start, off_t offset, int count, int *eof, void *data) {
	if (offset > 0) return 0;
	return scnprintf(buffer, count, "%d\n", (int)brightness);
}

static int proc_brightness_write(struct file *filp, const char __user *buffer, unsigned long len, void *data) {
	unsigned int newval;
	if (len >= sizeof(buf)) return -ENOSPC;
	if (copy_from_user(buf, buffer, len)) return -EFAULT;
	buf[len] = 0;

	if (sscanf(buf, "%u", &newval) == 1) {
		brightness = (short)(newval & 0xFF);

		if (button_dev) button_dev->brightness = brightness;

		SYMSEARCH_BIND_FUNCTION_TO(backlight, cpcap_direct_misc_write, _cpcap_direct_misc_write);
		if (_cpcap_direct_misc_write)
			_cpcap_direct_misc_write(g_reg, brightness_to_cpcap(brightness), g_mask_wr);
	}
	return len;
}

/*
 * Proc read/write for hook_enable
 */
static int proc_hook_read(char *buffer, char **start, off_t offset, int count, int *eof, void *data) {
	if (offset > 0) return 0;
	return scnprintf(buffer, count, "%u\n", (unsigned int)hooked);
}

static int proc_hook_write(struct file *filp, const char __user *buffer, unsigned long len, void *data) {
	unsigned int newval = 0;

	if (len >= sizeof(buf)) return -ENOSPC;
	if (copy_from_user(buf, buffer, len)) return -EFAULT;
	buf[len] = 0;

	if (sscanf(buf, "%u", &newval) == 1) {
		if (!newval && hooked) {
			hook_exit();
			hooked = 0;
		} else if (newval && !hooked) {
			hook_init();
			hooked = 1;
		}
	}
	return len;
}

/*
 * Proc read/write for log_enable
 */
static int proc_log_enable_read(char *buffer, char **start, off_t offset, int count, int *eof, void *data) {
	if (offset > 0) return 0;
	return scnprintf(buffer, count, "%d\n", (int)log_enable);
}

static int proc_log_enable_write(struct file *filp, const char __user *buffer, unsigned long len, void *data) {
	unsigned int enable = 0;

	if (len >= sizeof(buf)) return -ENOSPC;
	if (copy_from_user(buf, buffer, len)) return -EFAULT;
	buf[len] = 0;

	if (sscanf(buf, "%u", &enable) == 1) {
		log_enable = (short)(enable & 0x1);
		printk(KERN_INFO TAG ": log_enable set to %d\n", (int)log_enable);
	}
	return len;
}

/*
 * Original Led Interface - Robust symbol checking
 */
extern struct rw_semaphore leds_list_lock;
extern struct list_head leds_list;

static int find_led_brightness(void) {
	struct led_classdev *led_cdev;
	int ret = -1;

	down_read(&leds_list_lock);
	list_for_each_entry(led_cdev, &leds_list, node) {
		if (led_cdev->name && strcmp(led_cdev->name, CPCAP_BUTTON_DEV) == 0) {
			button_dev = led_cdev;
			ret = 0;
			break;
		}
	}
	up_read(&leds_list_lock);
	return ret;
}

struct hook_info g_hi[] = {
	HOOK_INIT(cpcap_regacc_write),
	HOOK_INIT_END
};

static int __init backlight_init(void) {
	struct proc_dir_entry *pe;

	printk(KERN_INFO TAG ": loading button backlight brightness fix v2.3\n");

	g_reg = CPCAP_BUTTON_BACKLIGHT;
	g_mask_wr = defy_plus ? CPCAP_BUTTON_WR_MASK_PLUS : CPCAP_BUTTON_WR_MASK_DEF;

	proc_root = proc_mkdir(TAG, NULL);
	if (proc_root) {
		pe = create_proc_read_entry("log_enable", 0666, proc_root, proc_log_enable_read, NULL);
		if (pe) pe->write_proc = proc_log_enable_write;
        
		pe = create_proc_read_entry("hook_enable", 0666, proc_root, proc_hook_read, NULL);
		if (pe) pe->write_proc = proc_hook_write;
        
		pe = create_proc_read_entry("brightness", 0666, proc_root, proc_brightness_read, NULL);
		if (pe) pe->write_proc = proc_brightness_write;
	}

	if (find_led_brightness() == 0) {
		if (brightness == 4) brightness = button_dev->brightness;
	}

	if (animate) brightness_fading(brightness);
    
	if (hook_enable) {
		hook_init();
		hooked = 1;
	}

	return 0;
}

static void __exit backlight_exit(void) {
	if (hooked) hook_exit();
	if (proc_root) {
		remove_proc_entry("brightness", proc_root);
		remove_proc_entry("log_enable", proc_root);
		remove_proc_entry("hook_enable", proc_root);
		remove_proc_entry(TAG, NULL);
	}
}

module_param(defy_plus, short, 0644);
MODULE_PARM_DESC(defy_plus,   "Defy (Froyo) or Defy+ (Gingerbread) kernel (0-1)");
module_param(animate , short, 0644);
MODULE_PARM_DESC(animate,     "Animation on module load (default 0)");
module_param(log_enable , short, 0644);
MODULE_PARM_DESC(log_enable,  "Enable dmesg logs (0/1)");
module_param(hook_enable , short, 0644);
MODULE_PARM_DESC(hook_enable, "Enable hook on cpcap, required if liblight is not present (default 0)");
module_param(brightness, short, 0644);
MODULE_PARM_DESC(brightness,  "Default brightness level (0-255)");

module_init(backlight_init);
module_exit(backlight_exit);

MODULE_VERSION("2.3");
MODULE_DESCRIPTION("Fix button backlight brightness level for Motorola OMAP3");
MODULE_AUTHOR("Tanguy Pruvot, CyanogenDefy, palmbeach05");
MODULE_LICENSE("GPL");
