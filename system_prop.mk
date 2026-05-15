# --- Shadow System Properties ---

# RIL and Telephony
PRODUCT_PROPERTY_OVERRIDES += \
    rild.libpath=/system/lib/libmoto_ril.so \
    rild.libargs=-d/dev/ttyS0 \
    ro.telephony.ril.v3=skipdatareg \
    ro.telephony.default_network=4 \
    ro.telephony.call_ring.delay=30 \
    ro.telephony.call_ring.multiple=false \
    ro.cdma.vm.number=*86 \
    cdma.nbpcd.supported=false
    ro.cdma.nbpcd=1 \
    ro.cdma.otaspnumschema=SELC,1,80,99 \
    ro.cdma.home.operator.alpha=Verizon \
    ro.cdma.home.operator.numeric=310004 \
    ro.cdma.homesystem=64,65,76,77,78,79,80,81,82,83 \
    ro.cdma.data_retry_config=default_randomization=2000,0,0,120000,180000,540000,960000 \
    ro.com.android.dataroaming=true \
    ro.mot.ril.danlist=611,*611,#611 \
    persist.ril.ecclist=911,*911,#911 \
    persist.ril.modem.mode=1 \
    persist.ril.features=0x07 \
    persist.ril.modem.ttydevice=/dev/usb/tty1-3:1.0 \
    persist.ril.mux.noofchannels=7 \
    persist.ril.mux.retries=500 \
    persist.ril.mux.sleep=2 \
    persist.ril.mux.ttydevice=/dev/ttyS0 \
    persist.ril.pppd.start.fail.max=16

# Networking and Connectivity
PRODUCT_PROPERTY_OVERRIDES += \
    net.dns1=8.8.8.8 \
    net.dns2=8.8.4.4 \
    softap.interface=wlan0 \
    wifi.interface=wlan0 \
    wifi.supplicant_scan_interval=120 \
    mobiledata.interfaces=ppp0

# Google Client IDs & Location
PRODUCT_PROPERTY_OVERRIDES += \
    ro.com.google.clientidbase.ms=android-verizon \
    ro.com.google.clientidbase.am=android-verizon \
    ro.com.google.clientidbase.gmm=android-motorola \
    ro.com.google.clientidbase.yt=android-verizon \
    ro.com.google.locationfeatures=1 \
    ro.com.google.gmsversion=4.4_r2

# Motorola Hardware Features
PRODUCT_PROPERTY_OVERRIDES += \
    ro.mot.eri=1 \
    ro.mot.hw.HAC=1 \
    ro.mot.deep.sleep.supported=true \
    ro.mot.hw.calibratedImager=1 \
    persist.mot.proximity.touch=1

# Graphics and User Interface
PRODUCT_PROPERTY_OVERRIDES += \
    ro.sf.lcd_density=240 \
    qemu.hw.mainkeys=1 \
    # LED charging indicator mode
    #  off   = keep LED off during charging
    #  white = white LED for 'charging', green LED for 'charged'
    #  rgb   = mixed yellowish LED for 'charging', green LED for 'charged'
    persist.sys.charge_led=rgb \
    persist.sys.button_brightness=30 \
    persist.sys.multitouch=2 \
    persist.sys.force_highendgfx=true \
    persist.call_recording.enabled=1

# RIL and Telephony (Verizon Specifics)
PRODUCT_PROPERTY_OVERRIDES += \
    ro.mot.eri.losalert.delay=2000 \
    ro.mot.eri.sidalert.delay=1000 \
    ro.cdma.sms.latin_encode=true \
    ro.mot.fid.33531.keylock_ecm=true \
    ro.mot.mynet=true

# Camera and Media Hardware
# These complement the OMAP3 settings in your init_omap3.c
PRODUCT_PROPERTY_OVERRIDES += \
    ro.media.enc.aud.fileformat=qcp \
    ro.media.enc.aud.codec=qcelp \
    ro.media.enc.aud.bps=13300 \
    ro.media.enc.aud.ch=1 \
    ro.media.enc.aud.hz=8000 \
    ro.media.capture.fast.fps=4 \
    ro.media.capture.slow.fps=60 \
    ro.media.capture.useDFR=1 \
    ro.media.camera.focal=3564.0,3564.0 \
    ro.media.camera.principal=1632.0,1224.0 \
    ro.media.capture.shuttertone=1 \
    ro.media.sensor.orient=90 \
    ro.media.panorama.defres=2048x1536 \
    ro.media.panorama.frameres=1280x720 \
    ro.media.capture.prevfps=28 \
    ro.media.camera.skew=0.0 \
    ro.media.camera.distortion=0.0,0.0,0.0,0.0,0.0 \
    ro.media.camera.calresolution=3264,2448 \
    media.stagefright.enable-record=false \
    media.stagefright.enable-rtsp=false
    
# System Performance & Hardware Sensors
PRODUCT_PROPERTY_OVERRIDES += \
    ro.min_pointer_dur=10 \
    mot.proximity.delay=450 \
    mot.proximity.distance=60 \
    ro.mot.bindervm.config=126 \
    ro.service.start.smc=1 \
    log.tag.launcher_force_rotate=VERBOSE \
    lockscreen.rot_override=true

ADDITIONAL_DEFAULT_PROPERTIES += \
    ro.secure=0
