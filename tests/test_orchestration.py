# SPDX-License-Identifier: Apache-2.0
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


casa = module('casa', ROOT / 'scripts/smoke-casa.py')
board = module('board', ROOT / 'scripts/board-job.py')


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL).decode().strip()


def init(path):
    path.mkdir()
    git(path, 'init', '-q')
    git(path, 'config', 'user.name', 'Test')
    git(path, 'config', 'user.email', 'test@example.invalid')


class SnapshotTests(unittest.TestCase):
    def test_exact_modified_nested_source_and_excluded_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested, source = root / 'dependency', root / 'source'
            init(nested)
            (nested / 'rtl.v').write_text('old rtl')
            git(nested, 'add', '.')
            git(nested, 'commit', '-qm', 'base')
            init(source)
            (source / 'hw/fpga').mkdir(parents=True)
            for rel in ('Cargo.lock', 'rust-toolchain.toml', 'hw/fpga/setup_fpga.sh', 'deleted.txt'):
                (source / rel).write_text('base')
            (source / '.gitignore').write_text('target/\n')
            git(source, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(nested), 'nested')
            git(source, 'add', '.')
            git(source, 'commit', '-qm', 'base')
            (source / 'nested/rtl.v').write_text('changed rtl')
            (source / 'nested/new.v').write_text('new rtl')
            (source / 'deleted.txt').unlink()
            (source / 'target').mkdir()
            (source / 'target/private-cache').write_text('must not sync')
            (source / '.git/hooks/private-hook').write_text('must not sync')
            out = root / 'out'
            out.mkdir()
            with patch.object(casa, 'ROOT', source):
                manifest = casa.snapshot(source, out / 'source', out)
            self.assertEqual((out / 'source/nested/rtl.v').read_text(), 'changed rtl')
            self.assertIn('nested/new.v', manifest['files'])
            self.assertNotIn('deleted.txt', manifest['files'])
            self.assertFalse((out / 'source/target').exists())
            self.assertFalse((out / 'source/.git/hooks/private-hook').exists())
            self.assertEqual(git(out / 'source', 'remote'), '')
            self.assertEqual(git(source, 'rev-parse', 'HEAD'), git(out / 'source', 'rev-parse', 'HEAD'))
            board.validate_snapshot(out / 'source', manifest)
            (out / 'source/nested/rtl.v').write_text('tampered')
            with self.assertRaisesRegex(RuntimeError, 'Content mismatch'):
                board.validate_snapshot(out / 'source', manifest)


class BoardTests(unittest.TestCase):
    def test_optional_sensor_failure_is_recorded(self):
        with patch.object(Path, 'read_text', side_effect=OSError(22, 'Invalid argument')):
            self.assertIn('unavailable', board.optional_read(Path('/sensor/temp')))

    def test_wrong_board_rejected(self):
        self.assertTrue(board.is_versal('aarch64', 'xlnx,versal\0'))
        self.assertFalse(board.is_versal('aarch64', 'xlnx,zynqmp\0'))
        self.assertFalse(board.is_versal('x86_64', 'xlnx,versal\0'))

    def test_zero_tests_and_nonzero_exit_never_pass(self):
        good = 'test smoke_test::smoke_test ... ok\ntest result: ok. 1 passed; 0 failed; 8 filtered out; finished in 1.25s'
        self.assertTrue(board.test_summary(good, 0)['passed'])
        self.assertFalse(board.test_summary(good, 1)['passed'])
        self.assertFalse(board.test_summary(good.replace('1 passed', '0 passed'), 0)['passed'])
        self.assertFalse(board.test_summary('', 0)['passed'])

    def test_busy_board_refuses_before_sync(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lockdir = root / '.cache/caliptra-vck190'
            lockdir.mkdir(parents=True)
            with (lockdir / 'uio0.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(Path, 'home', return_value=root), patch.object(board, 'identity', return_value={}), patch.dict(os.environ, {'XDG_CACHE_HOME': str(root / '.cache')}):
                    rc = board.worker('20261015T000000Z-1234abcd')
            self.assertEqual(rc, 75)
            status = json.loads((root / board.ROOT_NAME / 'runs/20261015T000000Z-1234abcd/status.json').read_text())
            self.assertFalse(status['passed'])
            self.assertFalse((root / board.ROOT_NAME / 'work').exists())


if __name__ == '__main__':
    unittest.main()
