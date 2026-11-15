"""Preference preservation and atomic local migration failure tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('migration_tests',Path(__file__).resolve().parents[1]/'tools/migrate_local.py')
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


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
