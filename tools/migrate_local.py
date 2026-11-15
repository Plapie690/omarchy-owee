#!/usr/bin/env python3
"""Install a committed OWEE candidate without discarding a local weather setup.

The default is a read-only dry run. --apply creates a verified backup and stages
a local Git clone before changing the bar. Pixel Weather's state paths remain
unchanged, and its old plugin folder is retained for rollback.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

OLD_ID = "local.paul.pixel-weather"
NEW_ID = "owee.weather"
ROOT = Path(__file__).resolve().parents[1]


def absolute(value):
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def safe_path(path):
    """Refuse symlinks in every existing component of a managed path."""
    path = absolute(path)
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Refusing symlink: {part}")
        if part != path and part.exists() and not part.is_dir():
            raise ValueError(f"Not a directory: {part}")
    return path


def safe_tree(root):
    safe_path(root)
    if root.exists():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Refusing symlink: {path}")
            if not path.is_dir() and not path.is_file():
                raise ValueError(f"Refusing special file: {path}")


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(command):
    env = os.environ.copy()
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Command failed: " + command[0])
    return result.stdout.strip()


def git(root, *args):
    return run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args])


def committed_source(source):
    safe_tree(source)
    if absolute(git(source, "rev-parse", "--show-toplevel")) != source:
        raise ValueError("Source must be the installable Git repository root")
    commit = git(source, "rev-parse", "--verify", "HEAD")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Source has uncommitted or untracked changes; commit the candidate first")
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("id") != NEW_ID:
        raise ValueError(f"Expected manifest id {NEW_ID}")
    if "manifest.json" not in git(source, "ls-files").splitlines():
        raise ValueError("manifest.json is not committed")
    run(["omarchy", "plugin", "validate", str(source)])
    return commit


def read_shell(path):
    safe_path(path)
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("shell.json is missing, not a regular file, or too large")
    raw = path.read_bytes()
    data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON value: " + value)))
    if not isinstance(data, dict):
        raise ValueError("shell.json must contain an object")
    return raw, data


def plugin_ref(value):
    if isinstance(value, str):
        return value if value in (OLD_ID, NEW_ID) else None
    if isinstance(value, dict) and value.get("id") in (OLD_ID, NEW_ID):
        return value["id"]
    return None


def replace_ids(value):
    if isinstance(value, str):
        return NEW_ID if value == OLD_ID else value
    if isinstance(value, list):
        preferred = next((i for i, item in enumerate(value) if plugin_ref(item) == OLD_ID), None)
        if preferred is None:
            preferred = next((i for i, item in enumerate(value) if plugin_ref(item) == NEW_ID), None)
        return [replace_ids(item) for i, item in enumerate(value)
                if plugin_ref(item) is None or i == preferred]
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            renamed = NEW_ID if key == OLD_ID else key
            replaced = replace_ids(item)
            if renamed in output and output[renamed] != replaced:
                raise ValueError("Conflicting old/new plugin settings keys; review them before migration")
            output[renamed] = replaced
        return output
    return value


def migrated_shell(data):
    data = json.loads(json.dumps(data))
    bar = data.get("bar", {})
    if not isinstance(bar, dict):
        raise ValueError("Unsupported bar configuration shape")
    layouts = bar.get("layout", {})
    if not isinstance(layouts, dict):
        raise ValueError("Unsupported bar.layout shape; no automatic placement change was made")
    references = [(section, index, plugin_ref(item)) for section, items in layouts.items()
                  if isinstance(items, list) for index, item in enumerate(items) if plugin_ref(item)]
    preferred = next((row for row in references if row[2] == OLD_ID), references[0] if references else None)
    if preferred:
        for section, items in layouts.items():
            if isinstance(items, list):
                layouts[section] = [item for index, item in enumerate(items)
                                    if not plugin_ref(item) or (section, index) == preferred[:2]]
    result = replace_ids(data)
    return result, {"section": preferred[0], "index": preferred[1]} if preferred else None


def fsync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path, data, mode=None):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path.parent)
    if mode is None:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=".owee-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data); output.flush(); os.fsync(output.fileno())
        safe_path(path)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_copy(source, target, mode=None):
    target = safe_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".owee-copy-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as content:
            os.fchmod(output.fileno(), mode if mode is not None else stat.S_IMODE(source.stat().st_mode))
            shutil.copyfileobj(content, output, length=65536)
            output.flush(); os.fsync(output.fileno())
        safe_path(target)
        os.replace(temporary, target)
        fsync_directory(target.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def state_files(directory):
    safe_path(directory)
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json")):
        safe_path(path)
        if not path.is_file():
            raise ValueError(f"State JSON is not a regular file: {path}")
        result.append(path)
    return result


@contextmanager
def transaction_lock(config):
    directory = safe_path(config / "omarchy")
    directory.mkdir(parents=True, exist_ok=True)
    path = safe_path(directory / ".owee-migration.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another OWEE migration or rollback is running") from error
        yield


def make_backup(config, state, shell, legacy, source_commit):
    root = safe_path(config / "omarchy/plugin-backups")
    root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="owee-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-", dir=root))
    if legacy.exists():
        safe_tree(legacy)
        shutil.copytree(legacy, backup / "legacy-plugin", copy_function=shutil.copy2)
    shutil.copy2(shell, backup / "shell.json")
    state_paths = state_files(state / "pixel-weather")
    (backup / "state").mkdir(mode=0o700)
    for path in state_paths:
        before = sha256(path)
        shutil.copy2(path, backup / "state" / path.name)
        if before != sha256(path) or before != sha256(backup / "state" / path.name):
            raise RuntimeError("State changed during backup; retry when the widget is idle")
    files = {}
    for path in sorted(backup.rglob("*")):
        if path.is_file():
            files[path.relative_to(backup).as_posix()] = {"sha256": sha256(path), "mode": stat.S_IMODE(path.stat().st_mode)}
    metadata = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "config_home": str(config), "state_home": str(state), "old_id": OLD_ID, "new_id": NEW_ID,
                "source_commit": source_commit, "state_files": [path.name for path in state_paths],
                "files": files, "legacy_plugin_present": legacy.exists()}
    atomic_write(backup / "backup.json", (json.dumps(metadata, indent=2) + "\n").encode())
    return backup, metadata


def verify_backup(backup, config, state):
    safe_tree(backup)
    manifest = backup / "backup.json"
    if not manifest.is_file() or manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Backup manifest is missing or too large")
    metadata = json.loads(manifest.read_text())
    if not isinstance(metadata, dict) or metadata.get("schema") != 1 or metadata.get("old_id") != OLD_ID or metadata.get("new_id") != NEW_ID:
        raise ValueError("Unsupported OWEE backup")
    if metadata.get("config_home") != str(config) or metadata.get("state_home") != str(state):
        raise ValueError("Backup belongs to different XDG roots; supply its original --config-home and --state-home")
    if not isinstance(metadata.get("files"), dict) or "shell.json" not in metadata["files"]:
        raise ValueError("Incomplete backup manifest")
    for relative, record in metadata["files"].items():
        if not isinstance(relative, str) or not isinstance(record, dict):
            raise ValueError("Invalid backup file record")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in ("state", "legacy-plugin", "shell.json"):
            raise ValueError("Unsafe backup path")
        content = safe_path(backup / path)
        if not content.is_file() or sha256(content) != record.get("sha256"):
            raise ValueError("Backup integrity failure: " + relative)
        if type(record.get("mode")) is not int or not 0 <= record["mode"] <= 0o777:
            raise ValueError("Invalid backup file mode")
    if not isinstance(metadata.get("state_files"), list):
        raise ValueError("Invalid backup state list")
    for name in metadata["state_files"]:
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".json") or "state/" + name not in metadata["files"]:
            raise ValueError("Invalid backed-up state filename")
    read_shell(backup / "shell.json")
    return metadata


def restart_shell(skip):
    if skip:
        return {"status": "skipped", "command": "omarchy restart shell"}
    result = subprocess.run(["omarchy", "restart", "shell"], capture_output=True, text=True, timeout=60)
    message = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return {"status": "restarted"}
    if "session is locked" in message.lower():
        return {"status": "pending", "reason": message, "command": "omarchy restart shell"}
    raise RuntimeError("Shell restart failed: " + message)


def migrate(args):
    source, config, state = safe_path(args.source), safe_path(args.config_home), safe_path(args.state_home)
    shell = safe_path(config / "omarchy/shell.json")
    plugins = safe_path(config / "omarchy/plugins")
    legacy, target = safe_path(plugins / OLD_ID), safe_path(plugins / NEW_ID)
    commit = committed_source(source)
    raw, document = read_shell(shell)
    changed, placement = migrated_shell(document)
    updated = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    shell_changed = changed != document
    safe_tree(legacy)
    if target.exists():
        if not target.is_dir() or committed_source(target) != commit:
            raise ValueError("Existing OWEE has a different or modified checkout; use native plugin update or review it first")
    states = state_files(state / "pixel-weather")
    origin = git(target, "remote", "get-url", "origin") if target.exists() else str(source)
    report = {"status": "dry_run", "source": str(source), "source_commit": commit,
              "target": str(target), "legacy_retained": str(legacy), "placement": placement,
              "shell_change": shell_changed, "state_files_preserved": len(states),
              "public_origin_pending": not origin.startswith("https://github.com/"), "git_origin": origin}
    if not args.apply:
        return report
    with transaction_lock(config):
        if target.exists() and not shell_changed:
            return {**report, "status": "already_installed", "restart": {"status": "not_needed"}}
        plugins.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".owee-stage-", dir=plugins))
        shell_written = False
        installed = target.exists()
        backup = None
        try:
            run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-hardlinks", "--", str(source), str(stage)])
            if committed_source(stage) != commit:
                raise RuntimeError("Staged checkout differs from the requested commit")
            if shell.read_bytes() != raw:
                raise RuntimeError("shell.json changed during staging; retry without overwriting it")
            backup, metadata = make_backup(config, state, shell, legacy, commit)
            verify_backup(backup, config, state)
            if not target.exists():
                os.replace(stage, target); fsync_directory(plugins); installed = True
            if shell.read_bytes() != raw:
                raise RuntimeError("shell.json changed before activation; original bar was left untouched")
            # Forward migration never writes user state; check it before activation can refresh caches.
            for name in metadata["state_files"]:
                if sha256(state / "pixel-weather" / name) != metadata["files"]["state/" + name]["sha256"]:
                    raise RuntimeError("State changed before activation; original bar was left untouched")
            if shell_changed:
                shell_written = True
                atomic_write(shell, updated)
            restarted = restart_shell(args.no_restart)
            return {**report, "status": "installed", "backup": str(backup), "restart": restarted,
                    "candidate_installed": installed, "state_unchanged_by_migration": True}
        except Exception as error:
            if shell_written:
                current = shell.read_bytes()
                if current == updated:
                    try:
                        atomic_copy(backup / "shell.json", shell, metadata["files"]["shell.json"]["mode"])
                    except OSError as restore_error:
                        raise RuntimeError(f"Migration failed and restoring the original bar also failed. Verified backup: {backup}. Restore it after resolving the filesystem error: {restore_error}") from error
                elif current != raw:
                    raise RuntimeError(f"Migration failed and shell.json changed externally; preserved that edit. Backup: {backup}. {error}") from error
            raise RuntimeError(f"Migration failed; original bar retained. Candidate may remain installed but inactive. Backup: {backup}. {error}") from error
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--config-home", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))))
    parser.add_argument("--state-home", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))))
    parser.add_argument("--apply", action="store_true", help="Apply the staged migration; default is a read-only dry run")
    parser.add_argument("--no-restart", action="store_true", help="Leave shell restart to the caller; useful for isolated tests")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(migrate(args), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
