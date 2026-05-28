#!/sbin/sh

LED="/sys/class/leds/usb/brightness"
STATUS="/sys/class/power_supply/battery/status"

while true; do
	state=$(cat "$STATUS" 2>/dev/null)

	if [ "$state" = "Charging" ] || [ "$state" = "Full" ]; then
		echo 255 > "$LED"
	else
		echo 0 > "$LED"
	fi

	sleep 5
done
