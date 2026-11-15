"""Release transaction regression tests, using real disposable Git repositories."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('release_tools', Path(__file__).resolve().parents[1]/'tools/promote.py')
promoter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promoter)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='owee-release-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(promoter, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.git('init','-q','-b','develop')
        self.git('config','user.name','Release Test')
        self.git('config','user.email','release@example.invalid')
        for name in ('Panel.qml','BarWidget.qml'):
            (self.root/name).write_text('version 1.3.0-rc.2')
        (self.root/'manifest.json').write_text('{"version":"1.3.0-rc.2"}')
        (self.root/'.gitignore').write_text('.release.lock\nreports/\n')
        self.git('add','.')
        self.git('commit','-qm','candidate')
        self.head = self.git('rev-parse','HEAD')

    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,text=True,stderr=subprocess.DEVNULL).strip()

    def unchanged(self):
        self.assertEqual(self.head,self.git('rev-parse','HEAD'))
        self.assertEqual('',self.git('status','--porcelain'))
        self.assertIn('rc.2',(self.root/'manifest.json').read_text())

    def test_success_publishes_matching_refs_without_touching_candidate(self):
        with patch.object(promoter,'qualify'):
            report=promoter.promote(promoter.source_digest(self.root)[0])
        self.unchanged()
        self.assertEqual(report['stable_commit'],self.git('rev-parse','main'))
        self.assertEqual(report['stable_commit'],self.git('rev-parse','v1.3.0'))
        self.assertNotIn('rc.',self.git('show','main:manifest.json'))

    def test_failed_qualification_keeps_refs_and_checkout(self):
        with patch.object(promoter,'qualify',side_effect=RuntimeError('native failed')):
            with self.assertRaises(RuntimeError):promoter.promote(promoter.source_digest(self.root)[0])
        self.unchanged()
        self.assertNotIn('refs/heads/main',self.git('show-ref'))

    def test_tag_conflict_during_prepare_does_not_publish_main(self):
        def conflict(*args):self.git('tag','v1.3.0',self.head)
        with patch.object(promoter,'qualify',side_effect=conflict):
            with self.assertRaises(subprocess.CalledProcessError):promoter.promote(promoter.source_digest(self.root)[0])
        self.unchanged()
        self.assertEqual(self.head,self.git('rev-parse','v1.3.0'))
        self.assertNotIn('refs/heads/main',self.git('show-ref'))

    def test_existing_tag_refuses_before_qualification(self):
        self.git('tag','v1.3.0')
        with patch.object(promoter,'qualify') as qualify:
            with self.assertRaises(ValueError):promoter.promote(promoter.source_digest(self.root)[0])
            qualify.assert_not_called()
        self.unchanged()

    def test_dirty_candidate_is_preserved(self):
        (self.root/'Panel.qml').write_text('user edit')
        with patch.object(promoter,'qualify'):
            with self.assertRaises(ValueError):promoter.promote(promoter.source_digest(self.root)[0])
        self.assertEqual('user edit',(self.root/'Panel.qml').read_text())

    def test_changed_source_digest_refuses_before_qualification(self):
        with patch.object(promoter,'qualify') as qualify:
            with self.assertRaises(ValueError):promoter.promote('old-digest')
            qualify.assert_not_called()
        self.unchanged()

    def test_checked_out_main_is_not_modified(self):
        self.git('branch','main')
        with tempfile.TemporaryDirectory() as temporary:
            worktree=Path(temporary)/'main'
            self.git('worktree','add',str(worktree),'main')
            try:
                with patch.object(promoter,'qualify') as qualify:
                    with self.assertRaises(ValueError):promoter.promote(promoter.source_digest(self.root)[0])
                    qualify.assert_not_called()
                self.assertEqual(self.head,self.git('rev-parse','main'))
            finally:self.git('worktree','remove',str(worktree))
        self.unchanged()
