How to compile Droid X kernel modules
------------------------------------

These external kernel modules require the Droid X kernel tree :

It is available at https://github.com/palmbeach05/shadow-kernel

Add to your repo manifest \<project path="kernel/motorola/shadow-kernel" name="palmbeach05/shadow-kernel" />

---

"repo sync" and then, in root of your android repo :

    . build/envsetup.sh
    breakfast shadow
    
    make kernel
    make device_modules

---

PS : Do not make menuconfig, or use make in kernel tree, if you have an error reporting
the kernel source is not clean, type before :

    make kernel_clean

