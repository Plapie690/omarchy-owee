"""Atomic JSON state, optimistic preference commits and bounded data caches."""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from network import strict_json

LIMIT = 1_000_000


def read_json(path, fallback):
    path = Path(path)
    candidates = [path, path.with_suffix(path.suffix+'.bak')] if path.name.endswith('settings.json') else [path]
    for candidate in candidates:
        try:
            if candidate.stat().st_size > LIMIT:
                continue
            value = strict_json(candidate.read_text())
            if path.name.endswith('settings.json') and not isinstance(value, dict): continue
            return value
        except (OSError, ValueError, TypeError, RecursionError):
            continue
    return fallback


def save_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > LIMIT:
        raise ValueError('State response too large')
    if path.name.endswith('settings.json') and path.exists():
        previous = read_json(path, None)
        if isinstance(previous, dict): save_json(path.with_suffix(path.suffix+'.bak'), previous)
    fd, temp = tempfile.mkstemp(prefix='.owee-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(encoded); out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally: fcntl.flock(stream, fcntl.LOCK_UN)


def commit_settings(path, before, after):
    with lock(path.parent/'.settings.lock'):
        if read_json(path, {}) != before:
            raise OSError('Preferences changed in another instance; please retry')
        if before:
            save_json(path.with_suffix(path.suffix+'.bak'), before)
        save_json(path, after)


def prune_weather(directory, protect=()):
    protected = {str(p) for p in protect}
    files = []
    for pattern in ('forecast-*.json', 'air-*.json'):
        for path in directory.glob(pattern):
            try: files.append((path.stat().st_mtime, path.stat().st_size, path))
            except OSError: pass
    total = sum(size for _, size, _ in files)
    count = len(files)
    for _, size, path in sorted(files):
        if total <= 32*1024*1024 and count <= 64: break
        if str(path) in protected: continue
        try: path.unlink(); total -= size; count -= 1
        except OSError: pass
