"""Preference preservation and atomic local migration failure tests."""
import importlib.util
import json
from argparse import Namespace
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('migration_tests',Path(__file__).resolve().parents[1]/'tools/migrate_local.py')
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
ROLLBACK_SPEC=importlib.util.spec_from_file_location('rollback_tests',Path(__file__).resolve().parents[1]/'tools/rollback_local.py')
r=importlib.util.module_from_spec(ROLLBACK_SPEC)
ROLLBACK_SPEC.loader.exec_module(r)


class MigrationTests(unittest.TestCase):
    def test_position_preferences_and_idempotence(self):
        old={'bar':{'layout':{'centerBegin':['clock',{'id':m.OLD_ID,'option':7}], 'right':[m.NEW_ID]}},'plugins':{m.OLD_ID:{'unit':'F'}}}
        original=json.dumps(old)
        new,position=m.migrated_shell(old)
        self.assertEqual(position,{'section':'centerBegin','index':1})
        self.assertEqual(new['bar']['layout']['centerBegin'][1],{'id':m.NEW_ID,'option':7})
        self.assertEqual(new['bar']['layout']['right'],[])
        self.assertEqual(new['plugins'][m.NEW_ID],{'unit':'F'})
        self.assertEqual(json.dumps(old),original)
        self.assertEqual(m.migrated_shell(new)[0],new)

    def test_conflicting_preferences_refuse(self):
        with self.assertRaises(ValueError):m.replace_ids({m.OLD_ID:{'unit':'C'},m.NEW_ID:{'unit':'F'}})

    def test_atomic_write_failure_keeps_previous_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'settings.json';path.write_bytes(b'original')
            with patch.object(m.os,'replace',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):m.atomic_write(path,b'new')
            self.assertEqual(path.read_bytes(),b'original')
            self.assertEqual([p.name for p in Path(t).iterdir()],['settings.json'])

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'real').write_text('state');(p/'link').symlink_to(p/'real')
            with self.assertRaises(ValueError):m.safe_path(p/'link')

    def test_backup_tampering_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);config=p/'config';state=p/'state';shell=config/'omarchy/shell.json'
            shell.parent.mkdir(parents=True);shell.write_text('{"bar":{}}')
            directory=state/'pixel-weather';directory.mkdir(parents=True);(directory/'settings.json').write_text('{"unit":"F"}')
            backup,metadata=m.make_backup(config,state,shell,config/'omarchy/plugins'/m.OLD_ID,'commit')
            self.assertEqual(m.verify_backup(backup,config,state),metadata)
            (backup/'state/settings.json').write_text('{}')
            with self.assertRaises(ValueError):m.verify_backup(backup,config,state)


class RollbackIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config, self.state = root / 'config', root / 'state'
        self.shell = self.config / 'omarchy/shell.json'
        self.shell.parent.mkdir(parents=True)
        self.shell.write_text(json.dumps({'bar': {'layout': {'right': [m.OLD_ID]}}}))
        self.settings = self.state / 'pixel-weather/settings.json'
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"unit":"F"}')
        self.legacy = self.config / 'omarchy/plugins' / m.OLD_ID
        self.legacy.mkdir(parents=True)
        (self.legacy / 'Main.qml').write_text('original plugin bytes')
        (self.legacy / 'Main.qml').chmod(0o640)
        (self.legacy / 'nested').mkdir()
        (self.legacy / 'nested/data.txt').write_text('nested data')
        self.backup, self.metadata = m.make_backup(
            self.config, self.state, self.shell, self.legacy, 'fixture-commit')
        shutil.rmtree(self.legacy)
        self.shell.write_text(json.dumps({'bar': {'layout': {'right': [m.NEW_ID]}}}))
        self.settings.write_text('{"unit":"C"}')
        self.current = (self.shell.read_bytes(), self.settings.read_bytes())
        self.args = Namespace(config_home=self.config, state_home=self.state,
                              backup=self.backup, apply=True, no_restart=True)

    def assert_current_untouched(self):
        self.assertEqual((self.shell.read_bytes(), self.settings.read_bytes()), self.current)
        self.assertFalse(self.legacy.exists())

    def test_unlisted_files_are_refused_before_any_restore(self):
        for name in ['legacy-plugin/Injected.qml', 'state/extra.json', 'extra.txt']:
            with self.subTest(name=name):
                extra = self.backup / name
                extra.write_text('unverified content')
                try:
                    with self.assertRaises(ValueError):
                        r.rollback(self.args)
                    self.assert_current_untouched()
                finally:
                    extra.unlink()

    def test_verified_restore_preserves_bytes_modes_and_backup(self):
        before = {p.relative_to(self.backup): p.read_bytes()
                  for p in self.backup.rglob('*') if p.is_file()}
        report = r.rollback(self.args)
        self.assertEqual(report['status'], 'restored')
        self.assertEqual(self.shell.read_bytes(), before[Path('shell.json')])
        self.assertEqual(self.settings.read_bytes(), before[Path('state/settings.json')])
        self.assertEqual((self.legacy / 'Main.qml').read_bytes(), b'original plugin bytes')
        self.assertEqual(stat.S_IMODE((self.legacy / 'Main.qml').stat().st_mode), 0o640)
        self.assertEqual({p.relative_to(self.legacy).as_posix() for p in self.legacy.rglob('*') if p.is_file()},
                         {'Main.qml', 'nested/data.txt'})
        self.assertEqual(before, {p.relative_to(self.backup): p.read_bytes()
                                  for p in self.backup.rglob('*') if p.is_file()})

    def test_file_added_after_initial_verification_is_refused(self):
        original = r.migration.verify_backup
        def inject(*args):
            metadata = original(*args)
            (self.backup / 'legacy-plugin/Injected.qml').write_text('unverified content')
            return metadata
        with patch.object(r.migration, 'verify_backup', side_effect=inject):
            with self.assertRaises(ValueError):
                r.rollback(self.args)
        self.assert_current_untouched()

    def test_file_changed_during_staging_is_refused_before_publication(self):
        original = r.migration.atomic_copy
        for name in ['state/settings.json', 'legacy-plugin/Main.qml']:
            with self.subTest(name=name):
                source = self.backup / name
                before = source.read_bytes()
                def tamper(src, destination, mode=None):
                    if src == source:
                        source.write_text('changed after verification')
                    return original(src, destination, mode)
                try:
                    with patch.object(r.migration, 'atomic_copy', side_effect=tamper):
                        with self.assertRaises(ValueError):
                            r.rollback(self.args)
                    self.assert_current_untouched()
                finally:
                    source.write_bytes(before)

    def test_symlink_inside_backup_is_refused(self):
        (self.backup / 'legacy-plugin/link.qml').symlink_to(self.shell)
        with self.assertRaises(ValueError):
            r.rollback(self.args)
        self.assert_current_untouched()
