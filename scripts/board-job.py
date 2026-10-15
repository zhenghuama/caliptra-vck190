#!/usr/bin/env python3
"""Offline VCK190 worker. All test timing originates in this process on the PS."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

ROOT_NAME = '.local/share/caliptra-vck190-casa'
RUN_RE = re.compile(r'^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$')


def atomic_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def capture(argv):
    p = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=30)
    return {'exit_code': p.returncode, 'output': p.stdout}


def is_versal(machine, compatible):
    return machine == 'aarch64' and 'xlnx,versal' in compatible.split('\0')


def identity():
    compatible = Path('/proc/device-tree/compatible').read_text()
    if not is_versal(os.uname().machine, compatible):
        raise RuntimeError('Refusing target: expected ARM64 Versal, not ZynqMP or a workstation')
    return {'model': Path('/proc/device-tree/model').read_text().strip('\0'),
            'compatible': compatible.strip('\0').split('\0'),
            'kernel': os.uname().release,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def optional_read(path):
    try:
        return path.read_text().strip()
    except OSError as exc:
        return {'unavailable': str(exc)}


def health():
    data = identity()
    data['cpus_online'] = Path('/sys/devices/system/cpu/online').read_text().strip()
    data['load_average'] = Path('/proc/loadavg').read_text().strip()
    data['free_bytes'] = shutil.disk_usage(Path.home()).free
    data['temperatures_millidegrees_c'] = {
        str(p): optional_read(p)
        for p in Path('/sys/class/thermal').glob('thermal_zone*/temp') if os.access(p, os.R_OK)}
    data['cpu_frequencies_khz'] = {
        str(p): optional_read(p)
        for p in Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_cur_freq')}
    data['failed_services'] = capture(['systemctl', '--failed', '--no-legend', '--no-pager'])
    return data


def setup_needed():
    name = Path('/sys/class/uio/uio0/name')
    if name.exists() and name.read_text().strip() != 'caliptra-fpga-uio-dev':
        raise RuntimeError('UIO0 belongs to a different device; refusing automatic setup')
    idle = [Path(f'/sys/devices/system/cpu/cpu{i}/cpuidle/state1/disable') for i in (0, 1)]
    return (not name.exists() or not os.access('/dev/uio0', os.R_OK | os.W_OK)
            or any(p.exists() and p.read_text().strip() != '1' for p in idle))


def validate_snapshot(source, manifest):
    for rel, spec in manifest['files'].items():
        if Path(rel).is_absolute() or '..' in Path(rel).parts:
            raise RuntimeError('Invalid snapshot path')
        path = source / rel
        if source.resolve() not in path.resolve().parents:
            raise RuntimeError(f'Snapshot path escapes source: {rel}')
        if spec['kind'] == 'symlink':
            if not path.is_symlink() or os.readlink(path) != spec['target']:
                raise RuntimeError(f'Symlink mismatch: {rel}')
        else:
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
                raise RuntimeError(f'Content mismatch: {rel}')
            if bool(path.stat().st_mode & 0o111) != spec['executable']:
                raise RuntimeError(f'Executable-mode mismatch: {rel}')


def test_summary(text, exit_code):
    result = re.search(r'test result: ok\. 1 passed; 0 failed;[^\n]*finished in ([0-9.]+)s', text)
    actual = 'test smoke_test::smoke_test ... ok' in text
    return {'passed': exit_code == 0 and actual and result is not None,
            'test_reported_seconds': float(result.group(1)) if result else None,
            'fpga_revisions': re.findall(r'FPGA built from ([0-9a-fA-F]+)', text),
            'runtime_boots': text.count('UART: Caliptra RT')}


def worker(run_id):
    if not RUN_RE.fullmatch(run_id):
        raise ValueError('Invalid run ID')
    base = Path.home() / ROOT_NAME
    run = base / 'runs' / run_id
    source = base / 'work' / 'caliptra-sw'
    run.mkdir(parents=True, exist_ok=True)
    status = {'run_id': run_id, 'measurement_location': 'VCK190 Arm PS'}

    def state(phase, **extra):
        status.update(phase=phase, **extra)
        atomic_json(run / 'status.json', status)

    def wait_for(name, seconds=600):
        deadline = time.monotonic() + seconds
        while not (run / name).exists():
            if (run / 'cancel').exists():
                raise RuntimeError('Preparation cancelled by casa')
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Timed out waiting for {name}')
            time.sleep(1)
        return json.loads((run / name).read_text())

    try:
        status['board'] = identity()
        lockdir = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'caliptra-vck190'
        lockdir.mkdir(parents=True, exist_ok=True)
        with (lockdir / 'uio0.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                state('done', exit_code=75, passed=False, error='Board is busy; no source sync was allowed')
                return 75
            if shutil.disk_usage(base).free < 3 * 1024**3:
                raise RuntimeError('Less than 3 GiB free on the board; clear old artifacts before running')
            source.mkdir(parents=True, exist_ok=True)
            state('waiting_for_sync')
            wait_for('ready.json')
            manifest = json.loads((run / 'source-manifest.json').read_text())
            state('verifying_source')
            validate_snapshot(source, manifest)
            status['source_commit'] = manifest['source_commit']
            status['source_tree_sha256'] = manifest['tree_sha256']
            if setup_needed():
                state('needs_setup')
                setup = wait_for('setup-result.json')
                if setup['exit_code'] != 0 or setup_needed():
                    raise RuntimeError('Board UIO/CPU-idle setup failed; see setup.log')
            atomic_json(run / 'health-before.json', health())
            env = os.environ.copy()
            # No host-side dependency proxy or credentials are passed to the board.
            env.update(CALIPTRA_SRC=str(source), CALIPTRA_LOG_DIR=str(run / 'test'),
                       CARGO_TARGET_DIR=str(base / 'target'), CARGO_NET_OFFLINE='true',
                       CALIPTRA_TEST_TIMEOUT='60m',
                       CALIPTRA_LOCK_FD=str(lock.fileno()))
            started = time.monotonic_ns()
            state('running', started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            with (run / 'console.log').open('w') as out:
                p = subprocess.run(['bash', str(run / 'run-fpga-smoke.sh')], env=env,
                                   stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                   pass_fds=(lock.fileno(),))
            elapsed = (time.monotonic_ns() - started) / 1e9
            console = (run / 'console.log').read_text(errors='replace')
            result = test_summary(console, p.returncode)
            atomic_json(run / 'health-after.json', health())
            kernel = capture(['journalctl', '-k', '-b', '--no-pager'])
            (run / 'kernel.log').write_text(kernel['output'])
            state('done', exit_code=p.returncode if p.returncode else (0 if result['passed'] else 3),
                  launcher_exit_code=p.returncode, launcher_wall_seconds=elapsed,
                  timing_scope='Board-local launcher wall time includes compilation; not a performance benchmark',
                  kernel_log_exit_code=kernel['exit_code'], **result)
            return status['exit_code']
    except Exception as exc:
        traceback.print_exc()
        state('done', exit_code=2, passed=False, error=str(exc))
        return 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id')
    sys.exit(worker(parser.parse_args().run_id))
