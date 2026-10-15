#!/usr/bin/env python3
"""Prepare locally, reserve/sync/test on the offline board, retrieve results."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = '.local/share/caliptra-vck190-casa'
RUN_RE = re.compile(r'^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def source_files(repo, prefix=Path('.'), revisions=None):
    """Include tracked edits/deletions and non-ignored additions, recursively."""
    revisions = revisions if revisions is not None else {}
    revisions[str(prefix)] = git(repo, 'rev-parse', 'HEAD').decode().strip()
    files = {}
    for item in git(repo, 'ls-files', '--stage', '-z').split(b'\0'):
        if not item:
            continue
        info, name = item.split(b'\t', 1)
        mode, _, stage = info.split()
        rel = Path(os.fsdecode(name))
        if stage != b'0':
            raise RuntimeError(f'Unresolved source merge: {prefix / rel}')
        path = repo / rel
        if mode == b'160000':
            if not (path / '.git').exists():
                raise RuntimeError(f'Uninitialized submodule {prefix / rel}; prepare sources on casa first')
            files.update(source_files(path, prefix / rel, revisions))
        elif path.exists() or path.is_symlink():
            files[str(prefix / rel)] = path
    for name in git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
        if name:
            rel = Path(os.fsdecode(name))
            files[str(prefix / rel)] = repo / rel
    return files


def snapshot(source, destination, output):
    source = source.resolve()
    if Path(git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != source:
        raise RuntimeError('CALIPTRA_SRC must be the root of a real Caliptra Git checkout')
    required = ['Cargo.lock', 'rust-toolchain.toml', 'hw/fpga/setup_fpga.sh']
    if not all((source / name).is_file() for name in required):
        raise RuntimeError('Source is not a prepared Caliptra checkout')
    revisions = {}
    files = source_files(source, revisions=revisions)
    # A minimal standalone .git is needed by Caliptra's firmware version builder.
    # Do not copy credentials, hooks, host Git config, or 1+ GiB of nested Git history.
    subprocess.run(['git', 'clone', '--quiet', '--no-checkout', '--depth=1',
                    '--single-branch', '--no-tags', source.as_uri(), str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'remote', 'remove', 'origin'], check=True)
    subprocess.run(['git', '-C', str(destination), 'reset', '--mixed', '--quiet', 'HEAD'], check=True)
    manifest = {'source_commit': revisions['.'], 'revisions': revisions,
                'infrastructure_commit': git(ROOT, 'rev-parse', 'HEAD').decode().strip(), 'files': {}}
    for rel, path in sorted(files.items()):
        if source not in path.resolve().parents:
            raise RuntimeError(f'Source path escapes checkout: {rel}')
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            value = os.readlink(path)
            if os.path.isabs(value):
                raise RuntimeError(f'Absolute source symlink cannot be deployed: {rel}')
            target.symlink_to(value)
            spec = {'kind': 'symlink', 'target': value}
        else:
            shutil.copy2(path, target)
            spec = {'kind': 'file', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'executable': bool(target.stat().st_mode & 0o111)}
        manifest['files'][rel] = spec
    manifest['tree_sha256'] = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'source.patch').write_bytes(git(source, 'diff', '--binary', 'HEAD'))
    return manifest


class Board:
    def __init__(self, host, control):
        if not re.fullmatch(r'[A-Za-z0-9_.@-]+', host) or host.startswith('-'):
            raise ValueError('Use a simple SSH host/alias or user@host')
        self.host = host
        self.base = ['ssh', '-o', f'ControlPath={control}', '-o', 'ConnectTimeout=10',
                     '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=15',
                     '-o', 'ServerAliveCountMax=3']
        self.common = self.base + ['-o', 'BatchMode=yes']

    def open(self):
        subprocess.run(self.base + ['-MNf', '-o', 'ControlMaster=yes', '-o', 'ControlPersist=120', self.host], check=True)

    def close(self):
        subprocess.run(self.common + ['-O', 'exit', self.host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self, argv, tty=False, check=True):
        p = subprocess.run(self.common + (['-tt'] if tty else []) + [self.host, shlex.join(map(str, argv))],
                           text=True, stdout=None if tty else subprocess.PIPE,
                           stderr=None if tty else subprocess.PIPE)
        if check and p.returncode:
            raise RuntimeError(f'Board command failed ({p.returncode}): {p.stderr or "see terminal"}')
        return p

    def python(self, code, *args):
        return self.run(['python3', '-c', code, *args]).stdout

    def sync(self, local, remote, delete=False, download=False):
        options = ['rsync', '-a', '--checksum', '--protect-args', '-e', shlex.join(self.common)]
        if delete:
            options += ['--delete', '--exclude=/target/']
        src, dst = str(local), f'{self.host}:{remote}'
        if download:
            src, dst = dst, src
        subprocess.run(options + [src, dst], check=True)


PROBE = '''import json,os,pathlib,shutil
p=pathlib.Path
compat=p('/proc/device-tree/compatible').read_text().split('\\0')
assert os.uname().machine=='aarch64' and 'xlnx,versal' in compat, 'Target is not ARM64 Versal; refusing'
assert shutil.which('rsync'), 'rsync is required on the board'
print(json.dumps({'home':str(p.home()),'model':p('/proc/device-tree/model').read_text().strip('\\0')}))
'''


def get_state(board, run):
    return json.loads(board.python('import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); print(p.read_text() if p.exists() else "{}")', run / 'status.json'))


def signal(board, run, filename, value):
    board.python('import pathlib,sys; p=pathlib.Path(sys.argv[1]); t=p.with_suffix(".tmp"); t.write_text(sys.argv[2]); t.replace(p)',
                 run / filename, json.dumps(value))


def collect(board, remote, local):
    local.mkdir(parents=True, exist_ok=True)
    board.sync(str(local) + '/', str(remote) + '/', download=True)
    status_path = local / 'status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    print(f'Results: {local}', flush=True)
    if status.get('phase') == 'done':
        print(f'{"PASS" if status.get("passed") else "FAIL"}: board exit {status.get("exit_code")}; '
              f'test duration {status.get("test_reported_seconds", "unavailable")} s', flush=True)
        if status.get('error'):
            print(status['error'], flush=True)
    else:
        print(f'Board state: {status.get("phase", "unknown")}; collect again after completion.', flush=True)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', default=os.environ.get('BOARD_HOST', 'ubuntu@192.168.77.2'))
    parser.add_argument('--source', default=os.environ.get('CALIPTRA_SRC', str(ROOT / 'work/caliptra-sw')))
    parser.add_argument('--collect-run')
    args = parser.parse_args()
    run_id = args.collect_run if args.collect_run is not None else time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8]
    if not RUN_RE.fullmatch(run_id):
        parser.error('RUN must be the exact run ID printed by smoke-casa')
    local = ROOT / 'logs' / 'smoke-casa' / run_id
    artifact = ROOT / 'artifacts' / 'smoke-casa' / run_id
    remote = None
    started = False
    execution_started = False
    with tempfile.TemporaryDirectory(prefix='cptra-ssh-') as control:
        board = Board(args.board, str(Path(control) / 'socket'))
        try:
            print(f'Run: {run_id}\nConnecting to {args.board} (normal SSH authentication)...', flush=True)
            board.open()
            info = json.loads(board.python(PROBE))
            base = Path(info['home']) / REMOTE_ROOT
            remote = base / 'runs' / run_id
            if args.collect_run is not None:
                status = collect(board, remote, local)
                return status.get('exit_code', 4)
            print('Preparing a recorded source snapshot on casa...', flush=True)
            artifact.mkdir(parents=True)
            manifest = snapshot(Path(args.source).resolve(), artifact / 'source', artifact)
            manifest['infrastructure_dirty'] = bool(git(ROOT, 'status', '--porcelain'))
            manifest['launcher_sha256'] = {}
            for name in ('board-job.py', 'run-fpga-smoke.sh', 'smoke-casa.py'):
                shutil.copy2(ROOT / 'scripts' / name, artifact / name)
                manifest['launcher_sha256'][name] = hashlib.sha256((artifact / name).read_bytes()).hexdigest()
            (artifact / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            print(f'Source: {manifest["source_commit"]}; {len(manifest["files"])} files; tree {manifest["tree_sha256"][:12]}', flush=True)
            # Refuse an unrelated pre-existing destination; use only our owned work tree.
            board.python('''import pathlib,sys
b=pathlib.Path(sys.argv[1]); r=pathlib.Path(sys.argv[2]); marker=b/'.smoke-casa-owned'
if b.resolve()!=b or (b/'work').is_symlink() or (b/'work/caliptra-sw').is_symlink(): raise SystemExit('Refusing symlinked deployment destination')
if b.exists() and not marker.exists(): raise SystemExit('Existing board directory lacks ownership marker')
b.mkdir(parents=True,exist_ok=True); marker.touch(); r.mkdir(parents=True,exist_ok=False)
''', base, remote)
            board.sync(artifact / 'board-job.py', str(remote / 'board-job.py'))
            board.sync(artifact / 'run-fpga-smoke.sh', str(remote / 'run-fpga-smoke.sh'))
            board.sync(artifact / 'source-manifest.json', str(remote / 'source-manifest.json'))
            # start_new_session + redirected streams keep recording if SSH/casa disconnects.
            board.python('''import pathlib,subprocess,sys
r=pathlib.Path(sys.argv[1]); out=(r/'worker.log').open('w')
p=subprocess.Popen(['python3',str(r/'board-job.py'),sys.argv[2]],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)
''', remote, run_id)
            started = True
            previous = None
            synced = False
            setup_sent = False
            last_notice = 0
            deadline = time.monotonic() + 2700
            while time.monotonic() < deadline:
                status = get_state(board, remote)
                phase = status.get('phase', 'starting')
                if phase != previous or time.monotonic() - last_notice >= 30:
                    print(f'Board: {phase} — run {run_id}', flush=True)
                    previous, last_notice = phase, time.monotonic()
                if phase == 'done':
                    result = collect(board, remote, local)
                    return result['exit_code']
                if phase == 'waiting_for_sync' and not synced:
                    print('Board lock acquired; syncing the dedicated source mirror...', flush=True)
                    board.sync(str(artifact / 'source') + '/', str(base / 'work/caliptra-sw') + '/', delete=True)
                    signal(board, remote, 'ready.json', {})
                    synced = True
                elif phase == 'needs_setup' and not setup_sent:
                    print('Board setup needs sudo (usually once after reboot). Enter the board password if prompted.', flush=True)
                    setup_command = ('set -o pipefail; sudo bash '
                                     + shlex.quote(str(base / 'work/caliptra-sw/hw/fpga/setup_fpga.sh'))
                                     + ' 2>&1 | tee ' + shlex.quote(str(remote / 'setup.log')))
                    setup = board.run(['bash', '-c', setup_command], tty=True, check=False)
                    signal(board, remote, 'setup-result.json', {'exit_code': setup.returncode})
                    setup_sent = True
                elif phase == 'running':
                    execution_started = True
                time.sleep(5)
            raise RuntimeError('Local wait limit reached; the remote worker retains its logs')
        except (Exception, KeyboardInterrupt) as exc:
            print(f'smoke-casa: {exc}', file=sys.stderr, flush=True)
            if started and remote is not None:
                try:
                    if not execution_started:
                        signal(board, remote, 'cancel', {})
                    collect(board, remote, local)
                except Exception as collection_error:
                    print(f'Result collection deferred: {collection_error}', file=sys.stderr)
                print(f'Recover with: make smoke-casa-results RUN={run_id} BOARD_HOST={shlex.quote(args.board)}', file=sys.stderr)
            return 2
        finally:
            board.close()


if __name__ == '__main__':
    sys.exit(main())
