#include <asm/uaccess.h>
#include <asm/cacheflush.h>
#include <asm/tlbflush.h>
#include <asm/io.h>
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/mutex.h>
#include <linux/cdev.h>
#include <linux/sched.h>
#include <linux/delay.h>
#include <linux/platform_device.h>
#include <linux/device.h>
#include <linux/suspend.h>
#include <asm/bootinfo.h>
#include <plat/panel.h>

#include "hboot.h"
#include "emu_uart.h"
#include "cache.h"

#define CTRL_DEVNAME "hbootctrl"

static int dev_major;

/* All descriptors share buffer selection and buffer lifetime through handoff. */
static DEFINE_MUTEX(hbootctrl_mutex);

/* NOTE: 0x00100000 is mapped per sector, keep that in mind */

#define MMU_48000000			0xFA000000
#define MMU_49000000			0xFB000000

#define MMU_SDMA_BASE			0xFA056000

#define MMU_UART3_BASE			0xFB020000

#define MMU_CM_FCLKEN_PER		0xFA005000
#define MMU_CM_ICLKEN_PER		0xFA005010

/* Clock is 48 MHz, divided by 16 */
#define UART_CLOCK_BASE_RATE	2995200

static int emu_uart_divisor(int uart_speed, uint16_t *divisor)
{
	uint32_t quotient;

	if (uart_speed <= 0)
		return -EINVAL;
	quotient = (uint32_t)UART_CLOCK_BASE_RATE / (uint32_t)uart_speed;
	if (quotient == 0 || quotient > 0x3FFF)
		return -EINVAL;
	*divisor = quotient;
	return 0;
}

/* Defensive software budget, not a verified hardware timing requirement. */
#define UART_POLL_TIMEOUT_US	1000000
#define UART_POLL_DELAY_US		1000

static int uart_wait(uint32_t address, uint32_t mask, uint32_t ready)
{
	unsigned int elapsed = 0;

	for (;;) {
		if ((__raw_readl(address) & mask) == ready)
			return 0;
		if (elapsed >= UART_POLL_TIMEOUT_US)
			return -ETIMEDOUT;
		udelay(UART_POLL_DELAY_US);
		elapsed += UART_POLL_DELAY_US;
	}
}

/* UART3's clock bits share registers with other peripherals. */
#define UART3_CLOCK_BIT		0x0800
#define UART3_REG(offset)	(MMU_UART3_BASE + (offset))

struct uart3_state {
	uint32_t fclk, iclk;
	uint32_t mdr1, lcr, efr, ier, dll, dlh;
	int configured;
};

static void restore_uart3(const struct uart3_state *state)
{
	unsigned long flags;

	local_irq_save(flags);
	if (state->configured) {
		__raw_writel(0x07, UART3_REG(0x20)); /* Disable UART mode */
		__raw_writel(0xBF, UART3_REG(0x0C));
		__raw_writel(state->dll, UART3_REG(0x00));
		__raw_writel(state->dlh, UART3_REG(0x04));
		__raw_writel(state->efr | (1 << 4), UART3_REG(0x08));
		__raw_writel(0x00, UART3_REG(0x0C));
		__raw_writel(state->ier, UART3_REG(0x04));
		__raw_writel(0xBF, UART3_REG(0x0C));
		__raw_writel(state->efr, UART3_REG(0x08));
		__raw_writel(state->lcr, UART3_REG(0x0C));
		__raw_writel(state->mdr1, UART3_REG(0x20));
	}
	__raw_writel((__raw_readl(MMU_CM_ICLKEN_PER) & ~UART3_CLOCK_BIT) |
		     state->iclk, MMU_CM_ICLKEN_PER);
	__raw_writel((__raw_readl(MMU_CM_FCLKEN_PER) & ~UART3_CLOCK_BIT) |
		     state->fclk, MMU_CM_FCLKEN_PER);
	local_irq_restore(flags);
}

static int reconfigure_emu_uart(int uart_speed, struct uart3_state *state)
{
	unsigned long flags;
	uint32_t fclk, iclk;
	uint16_t div;
	int ret;

	if (emu_uart_divisor(uart_speed, &div))
		return -EINVAL;

	local_irq_save(flags);
	fclk = __raw_readl(MMU_CM_FCLKEN_PER);
	iclk = __raw_readl(MMU_CM_ICLKEN_PER);
	state->fclk = fclk & UART3_CLOCK_BIT;
	state->iclk = iclk & UART3_CLOCK_BIT;
	state->configured = 0;
	__raw_writel(fclk | UART3_CLOCK_BIT, MMU_CM_FCLKEN_PER);
	__raw_writel(iclk | UART3_CLOCK_BIT, MMU_CM_ICLKEN_PER);
	local_irq_restore(flags);

	/* Wait for reset completion and an idle transmitter. A soft reset or
	 * FIFO clear would discard state we cannot restore on failure. */
	ret = uart_wait(UART3_REG(0x58), 1, 1);
	if (!ret)
		ret = uart_wait(UART3_REG(0x14), 0x60, 0x60);
	if (ret) {
		restore_uart3(state);
		printk(KERN_ERR CTRL_DEVNAME ": UART3 did not become ready\n");
		return ret;
	}

	/* Keep interrupt handlers away from the banked registers. */
	local_irq_save(flags);
	state->lcr = __raw_readl(UART3_REG(0x0C));
	state->mdr1 = __raw_readl(UART3_REG(0x20));
	__raw_writel(0x07, UART3_REG(0x20));
	__raw_writel(0xBF, UART3_REG(0x0C));
	state->efr = __raw_readl(UART3_REG(0x08));
	state->dll = __raw_readl(UART3_REG(0x00));
	state->dlh = __raw_readl(UART3_REG(0x04));
	__raw_writel(div & 0xFF, UART3_REG(0x00));
	__raw_writel(div >> 8, UART3_REG(0x04));
	__raw_writel(state->efr | (1 << 4), UART3_REG(0x08));
	__raw_writel(0x00, UART3_REG(0x0C));
	state->ier = __raw_readl(UART3_REG(0x04));
	__raw_writel(0x00, UART3_REG(0x04)); /* Disable IRQs */
	__raw_writel(0xBF, UART3_REG(0x0C));
	__raw_writel(0x00, UART3_REG(0x08)); /* Disable flow control */
	__raw_writel(0x03, UART3_REG(0x0C)); /* 8N1 */
	__raw_writel(0x00, UART3_REG(0x20)); /* UART 16x */
	state->configured = 1;
	local_irq_restore(flags);
	return 0;
}

int __attribute__((__naked__)) do_branch(void *bootlist, uint32_t bootsize,
				       uint32_t new_ttbl, void *func,
				       uint32_t p_emu_uart,
				       uint32_t p_powerup_reason,
				       uint16_t p_battery_status_at_boot,
				       uint8_t p_cid_recover_boot)
{
	__asm__ volatile (
		"sub    sp, sp, #0x10\n"
		"stmfd  sp!, {r0-r3}\n"
	);

	/* Reset SDMA */
	__raw_writel(__raw_readl(MMU_SDMA_BASE + 0x2C) | 2, MMU_SDMA_BASE + 0x2C);
	while (__raw_readl(MMU_SDMA_BASE + 0x28) != 1)
		;

	local_flush_tlb_all();
	v7_flush_kern_cache_all();

	/* Disable any caches */
	__asm__ volatile (
		"mov    r0, #0x00\n"

		/* Invalidate Cache */
		"mcr    p15, 0, r0, c7, c5, 0\n"
		"mcr    p15, 0, r0, c7, c5, 4\n"
		"mcr    p15, 0, r0, c7, c5, 6\n"

		/* Invalidate TLBs */
		"mcr    p15, 0, r0, c8, c7, 0\n"
		"mcr    p15, 0, r0, c8, c6, 0\n"
		"mcr    p15, 0, r0, c8, c5, 0\n"

		/* Barriers */
		"mcr     p15, 0, r0, c7, c10, 4\n"
		"mcr     p15, 0, r0, c7, c5, 4\n"

		/* Control Register */
		"mrc    p15, 0, r0, c1, c0, 0\n"

		/* Disable Branch Prediction & Instruction Cache */
		"bic    r0, r0, #0x1800\n" //-i -z

		/* Disable cache requests for everything (Instruction, Data, L2) */
		"bic    r0, r0, #0x0006\n" //-c -a
		"mcr    p15, 0, r0, c1, c0, 0\n"

		/* Auxiliary Control Register */
		"mrc    p15, 0, r0, c1, c0, 1\n"

		/* Disable L1 & L2 cache */
		"bic    r0, #0x02\n"
		"mcr    p15, 0, r0, c1, c0, 1\n"

		"ldmfd  sp!, {r0-r3}\n"
		"add    sp, sp, #0x10\n"

		/* OK - Ready to branch */
		"bx     r3\n"
	);

	return 0;
}

static void l1_map(uint32_t *table, uint32_t phys, uint32_t virt,
		   size_t sects, uint32_t flags)
{
	uint32_t physbase, virtbase;

	physbase = phys >> 20;
	virtbase = virt >> 20;
	while (sects-- > 0)
		table[virtbase++] = (physbase++ << 20) | flags;
}

#define L1_NORMAL_MAPPING (PMD_TYPE_SECT | PMD_SECT_AP_WRITE | PMD_SECT_WB)
#define L1_DEVICE_MAPPING (PMD_TYPE_SECT | PMD_SECT_AP_WRITE | PMD_SECT_UNCACHED)
void build_l1_table(uint32_t *table)
{
	memset(table, 0, 4 * 4096);
	l1_map(table, PHYS_OFFSET, PHYS_OFFSET, 512 - 12, L1_NORMAL_MAPPING);
	l1_map(table, PHYS_OFFSET, PAGE_OFFSET, 512 - 12, L1_NORMAL_MAPPING);
	l1_map(table, 0x48000000, MMU_48000000, 1, L1_NORMAL_MAPPING);
	l1_map(table, 0x49000000, MMU_49000000, 1, L1_NORMAL_MAPPING);
}

static int emu_uart = 0;
static int kill_dss = 0;
module_param(emu_uart, int, 0);
module_param(kill_dss, int, 0);

static int find_my_dev(struct device *dev, void *data);
#define to_platform_driver(x) container_of((x), struct platform_driver, driver)

static int disable_dss(void)
{
	int ret = -ENODEV;
	struct device *dev;
	struct platform_device *plat_dev;
	struct device_driver *drv;
	struct platform_driver *plat_drv;
	pm_message_t pt;

	dev = device_find_child(&platform_bus, "omapdss", find_my_dev);
	if (!dev) {
		printk("Could not find omapdss device\n");
		return -ENODEV;
	}
	drv = dev->driver;
	if (!drv) {
		printk("Could not find omapdss driver\n");
		goto out_put_device;
	}
	plat_drv = to_platform_driver(drv);

	plat_dev = to_platform_device(dev);

	if (!plat_drv->suspend) {
		printk("Could not find suspend in omapdss driver\n");
		ret = -EOPNOTSUPP;
		goto out_put_device;
	}
	pt.event = 0;
	ret = plat_drv->suspend(plat_dev, pt);
	if (ret)
		printk(KERN_ERR CTRL_DEVNAME ": omapdss suspend failed: %d\n", ret);

out_put_device:
	put_device(dev);
	return ret;
}

/* Caller holds hbootctrl_mutex through preparation and the transition. */
static int hboot_boot(int handle)
{
	bootfunc_t boot_entry;
	uint32_t bootsize, listsize;
	void *bootlist;
	uint32_t l1_mem, *l1_table;
	struct hboot_uart_route route;
	struct uart3_state uart_state;
	uint16_t uart_divisor;
	int ret;

	/* Zero disables UART; reject enabled rates before any boot preparation. */
	if (emu_uart && emu_uart_divisor(emu_uart, &uart_divisor))
		return -EINVAL;

	boot_entry = get_bootentry(&bootsize, handle);
	if (boot_entry == NULL) {
		printk(KERN_ERR CTRL_DEVNAME ": Failed to get boot entry\n");
		return -EINVAL;
	}

	l1_mem = get_high_pages(2);
	if (l1_mem == 0) {
		printk(KERN_INFO CTRL_DEVNAME ": Failed to allocate new l1 table\n");
		return -ENOMEM;
	}

	if (l1_mem & 0x3FFF) {
		free_high_pages((void *)l1_mem, 2);
		return -EINVAL;
	} else
		l1_table = (uint32_t *)l1_mem;

	build_l1_table(l1_table);

	bootlist = get_bootlist(&listsize, handle);
	if (bootlist == NULL) {
		printk(KERN_ERR CTRL_DEVNAME ": Failed to get bootlist\n");
		free_high_pages((void *)l1_mem, 2);
		return -ENOMEM;
	}

	if (emu_uart) {
		ret = hboot_activate_emu_uart(&route);
		if (ret)
			goto out_free_l1;
		ret = reconfigure_emu_uart(emu_uart, &uart_state);
		if (ret)
			goto out_restore_route;
	}

	/* Disable dss, some defy want it. */
	if (kill_dss) {
		ret = disable_dss();
		if (ret) {
			if (!emu_uart)
				goto out_free_l1;
			restore_uart3(&uart_state);
			goto out_restore_route;
		}
	}

	if (emu_uart)
		hboot_finish_emu_uart(&route, 1);

	/* Disable preempting */
	preempt_disable();
	local_irq_disable();
	local_fiq_disable();

	do_branch(bootlist, listsize, virt_to_phys(l1_table), boot_entry,
		  emu_uart, bi_powerup_reason(), bi_battery_status_at_boot(),
		  bi_cid_recover_boot());
	return -EBUSY;

out_restore_route:
	hboot_finish_emu_uart(&route, 0);
out_free_l1:
	free_high_pages((void *)l1_mem, 2);
	return ret;
}

static int hbootctrl_open(struct inode *inode, struct file *file);
static int hbootctrl_release(struct inode *inode, struct file *file);
static int hbootctrl_ioctl(struct inode *inode, struct file *file,
			   unsigned int cmd, unsigned long arg);
static int hbootctrl_write(struct file *file, const char __user *buf,
			   size_t count, loff_t *ppos);

static struct file_operations hbootctrl_ops = {
	.owner		= THIS_MODULE,
	.open		= hbootctrl_open,
	.release	= hbootctrl_release,
	.ioctl		= hbootctrl_ioctl,
	.write		= hbootctrl_write,
};

static int hbootctrl_open(struct inode *inode, struct file *file)
{
	printk(KERN_INFO CTRL_DEVNAME ": `open' stub called\n");
	return 0;
}

static int hbootctrl_release(struct inode *inode, struct file *file)
{
	printk(KERN_INFO CTRL_DEVNAME ": `release' stub called\n");
	return 0;
}

static int hbootctrl_ioctl(struct inode *inode, struct file *file,
			   unsigned int cmd, unsigned long arg)
{
	int ret;
	int handle;
	struct hboot_buffer_req buf_req;

	mutex_lock(&hbootctrl_mutex);
	ret = 0;
	switch (cmd) {
	case HBOOT_ALLOCATE_BUFFER:
		if (copy_from_user((void *)&buf_req, (void *)arg,
			   sizeof(struct hboot_buffer_req)) != 0) {
			ret = -EFAULT;
			break;
		}

		ret = allocate_buffer(buf_req.tag, buf_req.type, buf_req.attrs,
			      buf_req.size, buf_req.rest);
		break;

	case HBOOT_FREE_BUFFER:
		handle = (int)arg;
		ret = free_buffer(handle);
		break;

	case HBOOT_SELECT_BUFFER:
		handle = (int)arg;
		ret = select_buffer(handle);
		if (ret >= 0)
			file->f_pos = 0;

		break;

	case HBOOT_BOOT:
		handle = (int)arg;
		ret = hboot_boot(handle);
		break;

	default:
		ret = -ENOTTY;
		break;
	}
	mutex_unlock(&hbootctrl_mutex);
	return ret;
}

static int hbootctrl_write(struct file *file, const char __user *buf,
			   size_t count, loff_t *ppos)
{
	int ret;

	mutex_lock(&hbootctrl_mutex);
	ret = buffer_append_userdata(buf, count, ppos);
	mutex_unlock(&hbootctrl_mutex);
	return ret;
}

static int find_my_dev(struct device *dev, void *data)
{
	const char *drv_name = "UNKNOWN";

	if (dev->driver && dev->driver->name)
		drv_name = dev->driver->name;

	printk("dev[%s], driver[%s]\n", dev_name(dev), drv_name);
	if (!strcmp((char *)data, dev_name(dev))) {
		printk(KERN_INFO "Found it\n");
		return 1;
	}
	return 0;
}

int __init hbootmod_init(void)
{
	int ret;

	ret = buffers_init();
	if (ret < 0) {
		printk(KERN_ERR CTRL_DEVNAME ": Failed to initialize buffers table\n");
		return ret;
	}

	ret = register_chrdev(0, CTRL_DEVNAME, &hbootctrl_ops);
	if (ret < 0) {
		printk(KERN_ERR CTRL_DEVNAME ": Failed to register dev\n");
		buffers_destroy();
		return ret;
	}
	dev_major = ret;

	printk(KERN_INFO CTRL_DEVNAME ":  Successfully registered.\n");
	return 0;
}

static void __exit hbootmod_exit(void)
{
	unregister_chrdev(dev_major, CTRL_DEVNAME);
	buffers_destroy();
}

module_init(hbootmod_init);
module_exit(hbootmod_exit);
MODULE_LICENSE("GPL");
