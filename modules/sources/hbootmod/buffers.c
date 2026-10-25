#include <linux/slab.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <asm/uaccess.h>
#include "hboot.h"
#include "crc32.h"

#define GOOD_ADDRESS(p)				(__pa(p) >= 0x88c00000)
#define CHUNK_SIZE_ORDER			0
#define PAGES_PER_CHUNK				(1 << CHUNK_SIZE_ORDER)
#define CHUNK_SIZE						(PAGE_SIZE*PAGES_PER_CHUNK)

#pragma pack(push, 1)
struct plain_buffer
{
	struct abstract_buffer a;
	void *data;
};

struct scattered_buffer
{
	struct abstract_buffer a;
	uint32_t chunk_size;
	uint32_t allocated_chunks;
	uint32_t chunks[0];
};

struct nand_buffer
{
	struct abstract_buffer a;
	uint32_t offset;
};
#pragma pack(pop)

#define ABSTRACT(p) ((struct abstract_buffer*)p)
#define BUFFER_TAG(p) (ABSTRACT(p)->tag)
#define BUFFER_STATE(p) (ABSTRACT(p)->state)
#define BUFFER_TYPE(p) (ABSTRACT(p)->type)
#define BUFFER_ATTRS(p) (ABSTRACT(p)->attrs)
#define BUFFER_SIZE(p) (ABSTRACT(p)->size)
#define BUFFER_CHECKSUM(p) (ABSTRACT(p)->checksum)

struct generic_buffer
{
	union
	{
		struct plain_buffer *plain;
		struct scattered_buffer *scattered;
		struct nand_buffer *nand;
		struct abstract_buffer *abstract;

		void *generic;
	} container;
};

struct buffers_ctx
{
	int used;
	int handle;
	void *bootlist;
	struct generic_buffer bufs[MAX_BUFFERS_COUNT];
};

struct buffers_ctx buffers;

/* Runtime callers hold the control-interface operation mutex. */
static struct generic_buffer *get_buffer(int handle)
{
	if ((handle < 0) || (handle >= MAX_BUFFERS_COUNT) ||
	    (handle >= buffers.used) || (buffers.bufs[handle].container.generic == NULL))
		return NULL;

	return &buffers.bufs[handle];
}

static int get_new_buffer(struct generic_buffer **pbuf)
{
	int handle;

	/* Preserve last-slot reuse; reservation and publication are serialized. */
	if (buffers.used > 0 &&
	    buffers.bufs[buffers.used - 1].container.generic == NULL)
	{
		*pbuf = &buffers.bufs[buffers.used - 1];
		return buffers.used - 1;
	}

	/* used is the high-water extent; reuse holes without moving live handles. */
	for (handle = 0; handle < buffers.used - 1; ++handle)
	{
		if (buffers.bufs[handle].container.generic == NULL)
		{
			*pbuf = &buffers.bufs[handle];
			return handle;
		}
	}

	if (buffers.used >= MAX_BUFFERS_COUNT)
		return INVALID_BUFFER_HANDLE;

	handle = buffers.used++;
	*pbuf = &buffers.bufs[handle];
	(*pbuf)->container.generic = NULL;
	return handle;
}

/*
 * The device exposes 499 MiB (BoardConfig.mk). Limit each search to 128
 * allocations and 8 MiB of payload, plus a small tracking array. Order-0
 * chunks and the order-2 L1 table use at most 512 KiB and 2 MiB respectively;
 * the byte limit also bounds retries for larger plain buffers. Requests above
 * the byte limit fail rather than putting unbounded pressure on the host.
 * Charge kmalloc requests by whole buddy blocks, conservatively covering slab
 * rounding, and reserve that charge before allocating. No large stack array.
 */
#define HIGH_ALLOC_ATTEMPTS 128
#define HIGH_ALLOC_BYTES (8UL * 1024 * 1024)

static uint32_t get_high_allocation(size_t size, unsigned int order, int pages)
{
	uint32_t p = 0;
	uint32_t *rejected = NULL;
	unsigned int count = 0;
	unsigned int attempt;
	size_t charge;
	size_t retained = 0;

	if (pages)
	{
		if (order > get_order(HIGH_ALLOC_BYTES))
			return 0;
	}
	else
	{
		if (!size || size > HIGH_ALLOC_BYTES)
			return 0;
		order = get_order(size);
	}
	charge = PAGE_SIZE << order;

	for (attempt = 0; attempt < HIGH_ALLOC_ATTEMPTS; ++attempt)
	{
		if (charge > HIGH_ALLOC_BYTES - retained)
			break;
		if (pages)
			p = (uint32_t)__get_free_pages(GFP_KERNEL, order);
		else
			p = (uint32_t)kmalloc(size, GFP_KERNEL);
		if (!p || GOOD_ADDRESS(p))
			break;

		if (!rejected)
			rejected = kmalloc(HIGH_ALLOC_ATTEMPTS * sizeof(*rejected),
			                   GFP_KERNEL);
		if (!rejected)
		{
			if (pages)
				free_pages((unsigned long)p, order);
			else
				kfree((void*)p);
			p = 0;
			break;
		}
		rejected[count++] = p;
		retained += charge;
		p = 0;
	}

	while (count)
	{
		--count;
		if (pages)
			free_pages((unsigned long)rejected[count], order);
		else
			kfree((void*)rejected[count]);
	}
	kfree(rejected);
	return p;
}

uint32_t get_high_mem(size_t size)
{
	return get_high_allocation(size, 0, 0);
}

void free_high_mem(void *ptr)
{
	kfree(ptr);
}

uint32_t get_high_pages(unsigned int order)
{
	return get_high_allocation(0, order, 1);
}

void free_high_pages(void *p, unsigned int order)
{
	free_pages((unsigned long)p, order);
}

uint32_t get_high_page(void)
{
	return get_high_pages(0);
}

void free_high_page(void *p)
{
	return free_high_pages(p, 0);
}

static void init_abstract_buffer(struct abstract_buffer *ab, uint8_t tag, uint8_t type, uint8_t attrs, uint32_t size)
{
	ab->tag = tag;
	ab->state = B_STAT_NONE;
	ab->type = type;
	ab->attrs = attrs;
	ab->size = size;

#ifdef HBOOT_VERIFY_CRC32
	if (attrs & B_ATTR_VERIFY)
		crc32_init_ctx(&BUFFER_CHECKSUM(ab));
#endif
}

static void free_scattered_buffer(struct scattered_buffer *sc)
{
	uint32_t i;
	for (i = 0; i < sc->allocated_chunks; ++i)
		free_high_pages((void*)sc->chunks[i], CHUNK_SIZE_ORDER);

	free_high_mem((void*)sc);
}

static struct scattered_buffer *allocate_scattered_buffer(uint32_t bufsize, uint32_t rest)
{
	struct scattered_buffer *sc;
	uint32_t p;
	size_t sc_size;

	if (bufsize == 0)
		return NULL;

	sc_size = sizeof(struct scattered_buffer) + 4*((bufsize / CHUNK_SIZE) + (bufsize % CHUNK_SIZE ? 1 : 0));
	sc = (struct scattered_buffer*)get_high_mem(sc_size);
	if (sc == NULL)
		return NULL;

	sc->allocated_chunks = 0;
	sc->chunk_size = CHUNK_SIZE;
	while (bufsize > 0)
	{
		p = get_high_pages(CHUNK_SIZE_ORDER);
		if (p == 0)
			goto err;

		sc->chunks[sc->allocated_chunks++] = p;
		if (bufsize < sc->chunk_size)
			bufsize = 0;
		else
			bufsize -= sc->chunk_size;
	}
	return sc;
err:
	free_scattered_buffer(sc);
	return NULL;
}

static int append_scattered_buffer(struct scattered_buffer *sc, const char __user *data, size_t size, loff_t pos)
{
	size_t written = 0;
	size_t cur_size = 0;
	size_t uncopied;
	size_t copied;
	int chunk;
	int chunk_off;

	if (pos < 0 || pos >= BUFFER_SIZE(sc))
		return -EINVAL;

	if (size > BUFFER_SIZE(sc) - pos)
		size = BUFFER_SIZE(sc) - pos;

	chunk = (uint32_t)pos / sc->chunk_size;
	chunk_off = (uint32_t)pos % sc->chunk_size;
	while (written < size)
	{
		cur_size = min(size - written, (size_t)(sc->chunk_size - chunk_off));
		uncopied = copy_from_user((char*)sc->chunks[chunk] + chunk_off,
		                          data + written, cur_size);
		copied = cur_size - uncopied;
#ifdef HBOOT_VERIFY_CRC32
		if (copied && (BUFFER_ATTRS(sc) & B_ATTR_VERIFY))
			crc32_update(&BUFFER_CHECKSUM(sc), (const uint8_t*)sc->chunks[chunk] + chunk_off, copied);
#endif
		written += copied;
		if (uncopied)
			return written ? (int)written : -EFAULT;
		chunk++;
		chunk_off = 0;
	}
	return written;
}

static struct plain_buffer *allocate_plain_buffer(uint32_t bufsize, uint32_t rest) 
{
	struct plain_buffer *pb;

	pb = (struct plain_buffer*)get_high_mem(sizeof(struct plain_buffer));
	
	if (pb == NULL)
		return NULL;
	
	pb->data = (void*)get_high_mem(bufsize);
	
	if (pb->data == 0)
	{
		free_high_mem(pb);
		return NULL;
	}
	
	return pb;
}

static void free_plain_buffer(struct plain_buffer *pb) 
{
	free_high_mem(pb->data);
	free_high_mem(pb);
}

static int append_plain_buffer(struct plain_buffer *pb, const char __user *data, size_t size, loff_t pos)
{
	size_t uncopied;
	size_t copied;

	if (pos < 0 || pos >= BUFFER_SIZE(pb))
		return -EINVAL;

	if (size > BUFFER_SIZE(pb) - pos)
		size = BUFFER_SIZE(pb) - pos;

	uncopied = copy_from_user((char*)pb->data + pos, data, size);
	copied = size - uncopied;
#ifdef HBOOT_VERIFY_CRC32
	if (copied && (BUFFER_ATTRS(pb) & B_ATTR_VERIFY))
		crc32_update(&BUFFER_CHECKSUM(pb), (const uint8_t*)pb->data + pos, copied);
#endif
	if (uncopied && !copied)
		return -EFAULT;
	return (int)copied;
}

static struct nand_buffer *allocate_nand_buffer(uint32_t bufsize, uint32_t rest)
{
	struct nand_buffer *nd;

	nd = (struct nand_buffer*)get_high_mem(sizeof(struct nand_buffer));
	if (nd == NULL)
		return NULL;

	nd->offset = rest;
	return nd;
}

static void free_nand_buffer(struct nand_buffer *nd)
{
	free_high_mem(nd);
}

void free_typed_buffer(void *buffer, uint8_t type) 
{
	switch (type) 
	{
		case B_TYPE_PLAIN:
			free_plain_buffer((struct plain_buffer*)buffer);
			break;
		case B_TYPE_SCATTERED:
			free_scattered_buffer((struct scattered_buffer*)buffer);
			break;
		case B_TYPE_NAND:
			free_nand_buffer((struct nand_buffer*)buffer);
			break;
	}
}

int allocate_buffer(uint8_t tag, uint8_t type, uint8_t attrs, uint32_t bufsize, uint32_t rest)
{
	struct generic_buffer *buf;
	void *data;
	int handle;

	switch (type) 
	{
		case B_TYPE_PLAIN:
			data = allocate_plain_buffer(bufsize, rest);
			break;
		case B_TYPE_SCATTERED:
			data = allocate_scattered_buffer(bufsize, rest);
			break;
		case B_TYPE_NAND:
			data = allocate_nand_buffer(bufsize, rest);
			break;
		default:
			data = NULL;
			break;
	}

	if (data == NULL)
		return INVALID_BUFFER_HANDLE;

	handle = get_new_buffer(&buf);
	if (handle == INVALID_BUFFER_HANDLE) 
	{
		free_typed_buffer(data, type);
		return INVALID_BUFFER_HANDLE;
	}
	
	init_abstract_buffer(ABSTRACT(data), tag, type, attrs, bufsize);
	buf->container.generic = data;
	return handle;
}

int free_buffer(int handle) 
{
	struct generic_buffer *buf;
	uint8_t type;
	void *data;

	buf = get_buffer(handle);
	if (buf == NULL)
		return -1;

	data = buf->container.generic;
	type = BUFFER_TYPE(buf->container.abstract);
	buf->container.generic = NULL;
	if (buffers.handle == handle)
		buffers.handle = INVALID_BUFFER_HANDLE;

	free_typed_buffer(data, type);
	return 0;
}

int select_buffer(int handle) 
{
	if (get_buffer(handle) == NULL)
		return -EINVAL;

	buffers.handle = handle;
	return 0;
}

int buffer_append_userdata(const char __user *data, size_t size, loff_t *ppos) 
{
	struct generic_buffer *buf;
	int ret;

	buf = get_buffer(buffers.handle);
	if (buf == NULL)
		return -EINVAL;

	switch (BUFFER_TYPE(buf->container.abstract))
	{
		case B_TYPE_PLAIN:
			ret = append_plain_buffer(buf->container.plain, data, size, *ppos);
			break;
		case B_TYPE_SCATTERED:
			ret = append_scattered_buffer(buf->container.scattered, data, size, *ppos);
			break;
		default:
			ret = -EINVAL;
			break;
	}
	
	if (ret > 0)
		*ppos += ret;
	
	return ret;
}

bootfunc_t get_bootentry(uint32_t *bootsize, int handle) 
{
	struct generic_buffer *buf;
	bootfunc_t ret;

	buf = get_buffer(handle);
	
	if (buf == NULL)
		return NULL;

	if (BUFFER_TYPE(buf->container.abstract) != B_TYPE_PLAIN ||
	    BUFFER_SIZE(buf->container.abstract) < 4 ||
	    ((uint32_t)buf->container.plain->data) & 0x3)
		ret =  NULL;

	else 
	{
		ret = (bootfunc_t)buf->container.plain->data;
		*bootsize = BUFFER_SIZE(buf->container.plain);
	}

	return ret;
}

void *get_bootlist(uint32_t *listsize, int handle) 
{
	uint32_t *list;
	int i, j = 0;

	list = (uint32_t*)buffers.bootlist;
	for (i = 0; i < buffers.used; ++i) 
	{
		struct generic_buffer *buf;

		buf = &buffers.bufs[i];
		if (handle != i && buf->container.generic != NULL) 
		{
#ifdef HBOOT_VERIFY_CRC32
			if (BUFFER_ATTRS(buf->container.abstract) & B_ATTR_VERIFY)
				crc32_final(&BUFFER_CHECKSUM(buf->container.abstract));
#endif

			BUFFER_STATE(buf->container.abstract) = B_STAT_CREATED;
			list[j] = (uint32_t)buf->container.generic;
			j++;
		}
	}
	
	*listsize = j;
	return (void*)list;
}

int buffers_init(void)
{
	buffers.handle = INVALID_BUFFER_HANDLE;
	buffers.bootlist = (void*)get_high_mem(MAX_BUFFERS_COUNT*sizeof(void*));
	if (buffers.bootlist == NULL)
		return -1;
	return 0;
}

void buffers_destroy(void)
{
	if (buffers.bootlist)
		free_high_mem(buffers.bootlist);
}
