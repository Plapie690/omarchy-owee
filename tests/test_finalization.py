"""Finalization guard tests: no service, shell, Git checkout or notification changes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'finalization_tools', Path(__file__).resolve().parents[1] / 'tools/finalize_local.py')
finalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalizer)


class StopWaiting(Exception):
    """End a waiting test without waiting or triggering release work."""


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='owee-finalize-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report = self.root / 'summary.json'
        self.install = self.root / 'installed'
        self.write_report(status='running', qualified=False)
        for name, value in [('ROOT', self.root), ('REPORT', self.report),
                            ('INSTALL', self.install), ('EXPECTED_COMMIT', 'candidate'),
                            ('EXPECTED_DIGEST', 'digest')]:
            self.enterContext(patch.object(finalizer, name, value))
        self.enterContext(patch.object(sys, 'argv', ['finalize', '--candidate-commit',
                                                   'candidate', '--source-sha256', 'digest']))
        self.mutation = self.enterContext(patch.object(finalizer.subprocess, 'run'))
        self.save = self.enterContext(patch.object(finalizer, 'save'))

    def write_report(self, **changes):
        self.report.write_text(json.dumps({'source_sha256': 'digest', **changes}))

    def git_result(self, command, **kwargs):
        if command[0] == 'systemctl':
            return 'active'
        if command[-2:] == ['rev-parse', 'HEAD']:
            return 'candidate'
        if command[-3:] == ['remote', 'get-url', 'origin']:
            return str(self.root)
        if command[-2:] == ['status', '--porcelain']:
            return ''
        raise AssertionError('Unexpected command: ' + repr(command))

    def test_failed_or_unqualified_report_cannot_promote(self):
        for status, qualified in [('failed', False), ('interrupted', False), ('passed', False)]:
            with self.subTest(status=status):
                self.write_report(status=status, qualified=qualified, failures=['test failure'])
                with patch.object(finalizer, 'run', side_effect=self.git_result):
                    with self.assertRaisesRegex(RuntimeError, 'did not qualify'):
                        finalizer.main()
        self.mutation.assert_not_called()

    def test_running_report_waits_without_promoting(self):
        with patch.object(finalizer, 'run', side_effect=self.git_result), \
                patch.object(finalizer.time, 'sleep', side_effect=StopWaiting):
            with self.assertRaises(StopWaiting):
                finalizer.main()
        self.save.assert_called_once()
        self.assertEqual(self.save.call_args.args[0], 'waiting_for_endurance')
        self.mutation.assert_not_called()

    def test_stopped_endurance_with_running_report_cannot_promote(self):
        def stopped(command, **kwargs):
            return 'inactive' if command[0] == 'systemctl' else self.git_result(command, **kwargs)
        with patch.object(finalizer, 'run', side_effect=stopped):
            with self.assertRaisesRegex(RuntimeError, 'stopped without a final report'):
                finalizer.main()
        self.mutation.assert_not_called()

    def test_different_source_report_cannot_promote(self):
        self.write_report(status='passed', qualified=True, source_sha256='different-source')
        with patch.object(finalizer, 'run', side_effect=self.git_result):
            with self.assertRaisesRegex(RuntimeError, 'different source'):
                finalizer.main()
        self.mutation.assert_not_called()

    def test_changed_installed_checkout_is_preserved(self):
        def edited(command, **kwargs):
            if '-C' in command and command[-2:] == ['status', '--porcelain']:
                return ' M Panel.qml'
            return self.git_result(command, **kwargs)
        with patch.object(finalizer, 'run', side_effect=edited):
            with self.assertRaisesRegex(RuntimeError, 'Installed plugin has local changes'):
                finalizer.main()
        self.mutation.assert_not_called()

    def test_changed_candidate_commit_cannot_promote(self):
        def changed(command, **kwargs):
            if command == ['git', 'rev-parse', 'HEAD']:
                return 'different-candidate'
            return self.git_result(command, **kwargs)
        with patch.object(finalizer, 'run', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'Candidate HEAD changed'):
                finalizer.main()
        self.mutation.assert_not_called()

    def test_stalled_report_cannot_promote(self):
        os.utime(self.report, (0, 0))
        with patch.object(finalizer, 'run', side_effect=self.git_result):
            with self.assertRaisesRegex(RuntimeError, 'stopped progressing'):
                finalizer.main()
        self.mutation.assert_not_called()

    def test_check_only_calls_only_read_only_promotion_check(self):
        self.mutation.return_value = subprocess.CompletedProcess([], 1)
        with patch.object(sys, 'argv', [*sys.argv, '--check-only']), \
                patch.object(finalizer, 'run', side_effect=self.git_result):
            self.assertEqual(finalizer.main(), 1)
        self.mutation.assert_called_once()
        self.assertNotIn('--apply', self.mutation.call_args.args[0])
        self.save.assert_not_called()
