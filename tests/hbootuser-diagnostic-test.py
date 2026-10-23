#!/usr/bin/env python3
"""Host shell control-flow checks; does not emulate ARM or the stock kernel."""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'bootstrap/script/hbootuser-diagnostic.sh').read_text()


def check(case):
    with tempfile.TemporaryDirectory() as directory:
        base = pathlib.Path(directory)
        recovery = base / 'cache/recovery'
        recovery.mkdir(parents=True)
        marker = recovery / 'hbootuser-diagnostic.once'
        candidate = base / 'hbootuser-test'
        ran = base / 'ran'
        mounts = base / 'mounts'
        mounts.write_text('device /cache ext3 rw 0 0\n' if case != 'unavailable-cache' else '')
        bb = base / 'busybox'
        bb.write_text('''#!/bin/bash
case "$1" in
--list) printf '%s\\n' ash cat chmod mkdir rm sleep sync uname; exit;;
ash) shift; exec bash "$@";;
sleep) shift; /bin/sleep "$(python3 -c "print(float('$1') / 10)")"; exit;;
esac
exec "$@"
''')
        bb.chmod(0o755)
        if case != 'disabled':
            marker.touch()
        if case != 'missing-candidate':
            behavior = 'echo usage; echo stderr >&2; exit 1'
            if case == 'crash':
                behavior = 'kill -SEGV $$'
            elif case == 'timeout':
                behavior = 'exec /bin/sleep 30'
            candidate.write_text(f'#!/bin/bash\necho ran >> "{ran}"\n{behavior}\n')
            candidate.chmod(0o755)
        log = recovery / 'hbootuser-diagnostic.log'
        if case == 'logging-failure':
            log.mkdir()
        script = SOURCE.replace('/system/bootstrap/binary/busybox', str(bb))
        script = script.replace('/system/bootstrap/binary/hbootuser-test', str(candidate))
        script = script.replace('/cache/recovery', str(recovery))
        script = script.replace('/proc/mounts', str(mounts))
        path = base / 'probe.sh'
        path.write_text(script)
        subprocess.run(['bash', str(path)], timeout=8, capture_output=True, check=True)
        expected = case in ('successful-startup', 'crash', 'timeout')
        assert ran.exists() == expected, case
        assert marker.exists() != expected if case != 'disabled' else not marker.exists()
        if expected:
            output = log.read_text()
            assert 'Exit status:' in output, (case, output)
            if case == 'successful-startup':
                assert 'Exit status: 1' in output and 'stderr' in output
            if case == 'timeout':
                assert 'Watchdog expired' in output
            subprocess.run(['bash', str(path)], timeout=8, capture_output=True, check=True)
            assert ran.read_text() == 'ran\n', 'subsequent boot reran candidate'
        print(f'PASS {case}')


for name in ('disabled', 'missing-candidate', 'unavailable-cache', 'logging-failure',
             'successful-startup', 'crash', 'timeout'):
    check(name)

wrapper = (ROOT / 'bootstrap/binary/logwrapper').read_text()
assert wrapper.index('mount -t auto') < wrapper.index('ash /system/bootstrap/script/hbootuser-diagnostic.sh') < wrapper.index('if [ -e $BOOT_CONF ]')
original = subprocess.check_output(['git', 'show', 'HEAD:bootstrap/binary/logwrapper'], cwd=ROOT, text=True)
assert wrapper[wrapper.index('# Set cpu to 1ghz'):] == original[original.index('# Set cpu to 1ghz'):]
print('PASS unchanged recovery shortcut and menu; hook placement')
