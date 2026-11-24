#ifndef EMU_UART_H
#define EMU_UART_H

struct device;
struct spi_device;

#define HBOOT_ULPI_PADS 12

struct hboot_uart_route {
	struct device *cpcap;
	struct spi_device *spi;
	unsigned short ulpi[HBOOT_ULPI_PADS], uart_rx;
	unsigned short route_897, route_411;
	unsigned int writes_attempted;
};

int hboot_activate_emu_uart(struct hboot_uart_route *route);
void hboot_finish_emu_uart(struct hboot_uart_route *route, int keep);

#endif //EMU_UART_H
