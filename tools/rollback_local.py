#!/usr/bin/env python3
"""Restore an explicit OWEE migration backup; default is a read-only dry run.

The candidate plugin remains installed but is no longer referenced by the
restored bar. Backup files are verified and never modified by this command.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SPEC = importlib.util.spec_from_file_location("owee_local_migration", Path(__file__).with_name("migrate_local.py"))
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def rollback(args):
    config, state, backup = migration.safe_path(args.config_home), migration.safe_path(args.state_home), migration.safe_path(args.backup)
    metadata = migration.verify_backup(backup, config, state)
    shell = migration.safe_path(config / "omarchy/shell.json")
    legacy = migration.safe_path(config / "omarchy/plugins" / migration.OLD_ID)
    migration.read_shell(shell)
    targets = [(backup / "state" / name, migration.safe_path(state / "pixel-weather" / name), metadata["files"]["state/" + name]["mode"])
               for name in metadata["state_files"]]
    targets.append((backup / "shell.json", shell, metadata["files"]["shell.json"]["mode"]))
    if metadata.get("legacy_plugin_present") and legacy.exists():
        migration.safe_tree(legacy)
        for relative, record in metadata["files"].items():
            if not relative.startswith("legacy-plugin/") or "__pycache__" in Path(relative).parts or ".git" in Path(relative).parts:
                continue
            path = legacy / Path(relative).relative_to("legacy-plugin")
            if not path.is_file() or migration.sha256(path) != record["sha256"]:
                raise ValueError("Legacy plugin was edited after backup; refusing to overwrite those edits")
    report = {"status": "dry_run", "backup": str(backup), "shell": str(shell),
              "state_files_to_restore": metadata["state_files"], "candidate_retained": str(config / "omarchy/plugins" / migration.NEW_ID),
              "legacy_restore_needed": bool(metadata.get("legacy_plugin_present") and not legacy.exists())}
    if not args.apply:
        return report
    with migration.transaction_lock(config), tempfile.TemporaryDirectory(prefix=".owee-rollback-", dir=config / "omarchy") as temporary:
        journal = Path(temporary)
        snapshots = []
        for index, (_, target, _) in enumerate(targets):
            if target.exists():
                if not target.is_file():
                    raise ValueError("Restore target is not a regular file: " + str(target))
                copy = journal / str(index)
                shutil.copy2(target, copy)
                snapshots.append((target, copy))
            else:
                snapshots.append((target, None))
        restored = []
        legacy_created = False
        try:
            if report["legacy_restore_needed"]:
                legacy.parent.mkdir(parents=True, exist_ok=True)
                migration.safe_path(legacy.parent)
                staged = Path(tempfile.mkdtemp(prefix=".owee-legacy-", dir=legacy.parent))
                try:
                    shutil.copytree(backup / "legacy-plugin", staged, dirs_exist_ok=True)
                    os.replace(staged, legacy)
                    legacy_created = True
                    migration.fsync_directory(legacy.parent)
                finally:
                    if staged.exists():
                        shutil.rmtree(staged)
            for original, target, mode in targets:
                restored.append(target)
                migration.atomic_copy(original, target, mode)
            for original, target, _ in targets:
                if migration.sha256(original) != migration.sha256(target):
                    raise RuntimeError("Restored bytes do not match backup: " + str(target))
        except Exception:
            for target, snapshot in reversed(snapshots):
                if target not in restored:
                    continue
                if snapshot is None:
                    target.unlink(missing_ok=True)
                else:
                    migration.atomic_copy(snapshot, target)
            if legacy_created:
                shutil.rmtree(legacy)
            raise
        try:
            restart = migration.restart_shell(args.no_restart)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            restart = {"status": "pending", "reason": str(error), "command": "omarchy restart shell"}
        return {**report, "status": "restored", "restart": restart, "restored_bytes_verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--config-home", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))))
    parser.add_argument("--state-home", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))))
    parser.add_argument("--apply", action="store_true", help="Restore the verified backup; default is a read-only dry run")
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(rollback(args), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
