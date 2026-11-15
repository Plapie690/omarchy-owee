"""Small, privacy-preserving diagnostics; runtime stdout remains machine JSON."""
import json
import re
import sys


def report_error(operation, error):
    """Log fixed operation names and exception classes, never exception messages."""
    def clean(value):
        return re.sub(r'[^A-Za-z0-9_.-]', '_', str(value))[:80]
    record = {'event': 'owee.error', 'operation': clean(operation),
              'error_type': clean(type(error).__name__)}
    try:
        print(json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)
    except OSError:
        # A closed logging stream must not discard valid weather or preferences.
        pass
