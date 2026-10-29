PDS backup tests on a computer
=============================

Requirements
------------
Use a Linux or macOS computer with Python 3.8 or newer and /bin/sh.
On Windows, use a Linux environment through WSL and follow these steps there.
The harness was verified on Linux with Python 3.9.25 and /bin/sh (Bash).
macOS and WSL were not tested in this coding environment.

You do not need root, sudo, adb, Android tools, a connected phone, or any
third-party Python packages. Do not run these tests on your phone.

How to run
----------
1. Open your computer's Terminal application (or a WSL terminal).
2. Type cd followed by the path to your repository folder, then press Enter.
   For example, if the folder is under your home directory:

       cd "$HOME/android_device_motorola_shadow"

   Use your actual folder location. This is the repository root: it contains
   both the bootstrap and tests folders.
3. Check Python by running:

       python3 --version

   The version should be 3.8 or newer.
4. Run this exact command from the repository root:

       python3 -m unittest discover -s tests -p 'test_pdsbackup.py' -v

The verified command prints these five test names, each ending in "ok":

    test_dd_failure
    test_mount_failure_existing_image
    test_mount_failure_new_image
    test_success
    test_unreviewed_source_is_rejected

The final lines should look like this (the time varies):

    Ran 5 tests in 2.981s

    OK

Reading the results
-------------------
The tests check the script's actual shell control flow:

* A failed image copy exits unsuccessfully, publishes no image, never sets up
  a loop or mounts, skips permissions, and removes the temporary partial copy.
* A failed mount after copying exits unsuccessfully, detaches the dummy loop,
  skips permissions, and cleans up the invocation's temporary directory.
* A failed mount with an existing image detaches the dummy loop and preserves
  the existing image's bytes without copying or publishing another image.
* A successful copy publishes the image before mounting. Only after mounting
  succeeds do dummy ownership and group changes run for pds and battd.
* An unreviewed script is rejected before the shell can execute it.

For example, "Unexpected permission operation: ['chown', ...]" means a
failure path reached a permission change when it should have exited earlier.
"Loop device was not detached" means the mount failure cleanup was missing.
An ERROR containing "Unreviewed pdsbackup.sh" means the source fingerprint
changed. Review the complete script, path substitutions, and command doubles
before updating REVIEWED_SHA256; do not simply bypass that safety check.
Keep the full terminal output when reporting a failure.

How the tests stay on the computer
---------------------------------
The production script is read but never executed directly or modified. Its
complete reviewed contents are checked with SHA-256 before a temporary copy
is adapted. All /system, /data, /pds, /sys, /proc, and /dev paths (including
the PATH override, awk comparison, and dd operands) point inside a new
temporary directory. An additional scan rejects leftover absolute paths.
Any source change requires a fresh safety review, including new commands.

Only that copy runs under /bin/sh with a fresh environment and a PATH that
contains only controlled Python command doubles. BusyBox is also a double.
No real dd, mount, umount, losetup, chown, or chgrp is executed. Dummy find
handles -exec through controlled chown/chgrp doubles, never the host tools.
Other external commands are doubles too; no host awk or find is needed.
Partition bytes, sector counts, and mount information are temporary fixtures.
Every double records its arguments and execution order inside the temporary
directory. Unexpected double operations fail with diagnostic stderr.
TemporaryDirectory removes only the harness-created resources after each test.

These tests check failure handling with dummy commands. They do not replace
your successful device boot test or prove hardware compatibility. They do
not exercise a real partition, kernel mount, BusyBox implementation, filesystem
permissions, or physical device. A successful mount intentionally leaves the
dummy loop attached, matching the production script's intended behavior;
there is no real loop device to clean up.
