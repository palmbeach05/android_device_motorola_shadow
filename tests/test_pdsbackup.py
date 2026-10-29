"""Computer-only control-flow tests; see README.txt before running."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "bootstrap/script/pdsbackup.sh"
# This pins the complete, manually inspected shell program, including commands.
# Source changes require reviewing the entire adaptation before updating this.
REVIEWED_SHA256 = "ee4c61eb6ec1fef7b32dfb8d161217ddeaef4d1f05e532e5aa46ed4dfc59c46f"
COMMANDS = "awk chgrp chown dd find losetup mkdir mktemp mount mv rm rmdir umount wc".split()


def adapt(source, root):
    if hashlib.sha256(source).hexdigest() != REVIEWED_SHA256:
        raise ValueError("Unreviewed pdsbackup.sh: review all paths and commands before adapting")
    script = source.decode("utf-8")
    # Include the interpreter, PATH override, awk string, and dd operands.
    for prefix in ("/system", "/data", "/pds", "/sys", "/proc", "/dev"):
        script = re.sub(re.escape(prefix) + r"(?=/|\b)", str(root) + prefix, script)
    # No absolute path may survive outside our fresh temporary directory.
    without_root = script.replace(str(root) + "/", "SANDBOX/")
    if re.search(r"(?<![\w$])/[A-Za-z]", without_root):
        raise ValueError("Unexpected absolute path in adapted script")
    return script


def double(name, args):
    """Implement only reviewed operations; never delegate to host disk tools."""
    root = Path(os.environ["PDS_TEST_ROOT"]).resolve()

    def local(value):
        path = Path(value)
        if not path.is_absolute() or root not in path.resolve().parents:
            raise ValueError("Path outside test directory: " + value)
        return path

    if name == "busybox":
        name, *args = args
    if name not in COMMANDS:
        raise ValueError("Unexpected command: " + name)
    with (root / "commands.jsonl").open("a") as log:
        log.write(json.dumps([name] + args) + "\n")
    mode = os.environ["PDS_TEST_MODE"]
    if name == "mkdir":
        assert args[0] == "-p"
        local(args[1]).mkdir(parents=True, exist_ok=True)
    elif name == "rm":
        assert args[0] == "-f"
        local(args[1]).unlink(missing_ok=True)
    elif name == "rmdir":
        local(args[0]).rmdir()
    elif name == "mktemp":
        assert args == ["-d", str(root / "data/pdsbackup.XXXXXX")]
        print(tempfile.mkdtemp(prefix="pdsbackup.", dir=root / "data"))
    elif name == "dd":
        assert len(args) == 3 and args[2] == "bs=4096"
        assert args[0] == "if=" + str(root / "dev/block/mmcblk1p7")
        assert args[1].startswith("of=")
        destination = local(args[1][3:])
        payload = local(args[0][3:]).read_bytes()
        destination.write_bytes(payload[:17] if mode == "dd_failure" else payload)
        if mode == "dd_failure":
            return 1
    elif name == "awk":
        program, filename = args
        path = local(filename)
        if path == root / "proc/mounts":
            assert program == '$2 == "' + str(root / "pds") + '" { print $2 }'
            for line in path.read_text().splitlines():
                if line.split()[1] == str(root / "pds"):
                    print(line.split()[1])
        else:
            assert path == root / "sys/class/block/mmcblk1p7/size"
            assert 'size = $1 * 512' in program
            print(int(path.read_text()) * 512)
    elif name == "wc":
        assert args == ["-c"]
        print(len(sys.stdin.buffer.read()))
    elif name == "mv":
        assert args[0] == "-n"
        source, destination = map(local, args[1:])
        if not destination.exists():
            source.rename(destination)
    elif name == "losetup":
        loop = str(root / "dev/loop-test")
        if args == ["-f"]:
            print(loop)
        elif args == ["-d", loop]:
            (root / "loop-attached").unlink()
        else:
            assert args == [loop, str(root / "data/pdsdata.img")]
            assert local(args[1]).is_file()
            (root / "loop-attached").touch()
    elif name == "mount":
        assert args == ["-o", "rw,nosuid,nodev,noatime,nodiratime,barrier=1",
                        str(root / "dev/loop-test"), str(root / "pds")]
        if mode == "mount_failure":
            return 1
        (root / "mounted").touch()
    elif name == "umount":
        assert args == [str(root / "pds")]
    elif name == "find":
        target = local(args[0])
        assert target in (root / "pds", root / "data/battd")
        assert (root / "mounted").exists(), "find ran before successful mount"
        index = args.index("-exec")
        command, owner, placeholder, terminator = args[index + 1:]
        assert command in ("chown", "chgrp")
        assert (owner, placeholder, terminator) == ("1000", "{}", ";")
        # Simulate a matching entry and execute the controlled -exec double.
        return subprocess.run([str(root / "system/xbin" / command), owner,
                               str(target / "dummy-entry")], check=False).returncode
    elif name in ("chown", "chgrp"):
        assert (root / "mounted").exists(), name + " ran before successful mount"
        assert args[0] == "1000"
        local(args[1])
    return 0


class PdsBackupTests(unittest.TestCase):
    def run_script(self, mode, existing=False):
        temporary = tempfile.TemporaryDirectory(prefix="pdsbackup-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        script = adapt(SOURCE.read_bytes(), root)
        for directory in ("data/battd", "pds/public", "system/bin", "system/xbin",
                          "system/bootstrap/binary", "dev/block", "proc",
                          "sys/class/block/mmcblk1p7"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "dev/block/mmcblk1p7").write_bytes(b"P" * 1024)
        (root / "sys/class/block/mmcblk1p7/size").write_text("2\n")
        (root / "proc/mounts").write_text(
            "fake " + str(root / "pds") + " ext3 rw 0 0\n")
        if existing:
            (root / "data/pdsdata.img").write_bytes(b"existing backup")
        wrapper = root / "double"
        wrapper.write_text(
            "#!" + sys.executable + "\n"
            "import os, sys\n"
            "os.execv(sys.executable, [sys.executable, " + repr(str(Path(__file__).resolve()))
            + ", '--double', os.path.basename(sys.argv[0])] + sys.argv[1:])\n")
        wrapper.chmod(0o700)
        for command in COMMANDS:
            (root / "system/xbin" / command).symlink_to(wrapper)
        (root / "system/bootstrap/binary/busybox").symlink_to(wrapper)
        adapted = root / "pdsbackup.sh"
        adapted.write_text(script)
        # A fresh environment prevents inherited shell hooks or host PATH fallback.
        result = subprocess.run(["/bin/sh", str(adapted)], cwd=root,
                                env={"PATH": str(root / "system/xbin"),
                                     "PDS_TEST_ROOT": str(root), "PDS_TEST_MODE": mode,
                                     "LC_ALL": "C"},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.stderr, "", "Double rejected an operation: " + result.stderr)
        events = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
        self.assertFalse(list((root / "data").glob("pdsbackup.*")), "Temporary image directory leaked")
        return root, result, events

    def assert_no_permissions(self, events):
        for event in events:
            self.assertNotIn(event[0], ("find", "chown", "chgrp"),
                             "Unexpected permission operation: " + repr(event))

    def test_dd_failure(self):
        root, result, events = self.run_script("dd_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((root / "data/pdsdata.img").exists(), "Failed image was published")
        for event in events:
            self.assertNotIn(event[0], ("mv", "losetup", "mount"), "Unexpected operation: " + repr(event))
        self.assert_no_permissions(events)
        self.assertIn("dd", [event[0] for event in events])
        self.assertEqual([event[0] for event in events[-2:]], ["rm", "rmdir"])

    def check_mount_failure(self, existing):
        root, result, events = self.run_script("mount_failure", existing=existing)
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_permissions(events)
        names = [event[0] for event in events]
        mount_index = names.index("mount")
        self.assertEqual(events[mount_index + 1], ["losetup", "-d", str(root / "dev/loop-test")])
        self.assertFalse((root / "loop-attached").exists(), "Loop device was not detached")
        expected = b"existing backup" if existing else b"P" * 1024
        self.assertEqual((root / "data/pdsdata.img").read_bytes(), expected)
        if existing:
            self.assertNotIn("dd", names, "Existing backup was copied over")
            self.assertNotIn("mv", names, "Existing backup was replaced")
        else:
            self.assertLess(names.index("dd"), names.index("mv"))
            self.assertLess(names.index("mv"), mount_index)

    def test_mount_failure_new_image(self):
        self.check_mount_failure(existing=False)

    def test_mount_failure_existing_image(self):
        self.check_mount_failure(existing=True)

    def test_success(self):
        root, result, events = self.run_script("success")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((root / "data/pdsdata.img").read_bytes(), b"P" * 1024)
        names = [event[0] for event in events]
        self.assertLess(names.index("dd"), names.index("mv"))
        self.assertLess(names.index("mv"), names.index("mount"))
        self.assertLess(names.index("umount"), names.index("mount"))
        for command in ("find", "chown", "chgrp"):
            self.assertEqual(names.count(command), 4 if command == "find" else 2,
                             "Missing permission operations: " + repr(events))
            self.assertLess(names.index("mount"), names.index(command))
        self.assertNotIn(["losetup", "-d", str(root / "dev/loop-test")], events)

    def test_unreviewed_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            adapt(SOURCE.read_bytes() + b"\nmount /unexpected\n", Path("/unused"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--double":
        sys.exit(double(sys.argv[2], sys.argv[3:]))
    unittest.main()
