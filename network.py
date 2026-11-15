"""Bounded HTTPS JSON transport for the public weather services."""
import json
import math
import time
from typing import Any, Mapping, NoReturn
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOSTS = frozenset(('api.open-meteo.com', 'geocoding-api.open-meteo.com', 'air-quality-api.open-meteo.com'))
LIMIT = 1_000_000
USER_AGENT = 'OWEE/1.3 (non-commercial desktop weather)'


class NetworkError(OSError):
    def __init__(self, reason: str, retry_after: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


def validate_url(url: str) -> None:
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc not in HOSTS or p.username or p.password:
        raise ValueError('Weather source refused')


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def strict_json(data: str | bytes) -> Any:
    def invalid(value: str) -> NoReturn:
        raise ValueError('Non-finite JSON number')
    def finite(value: str) -> float:
        number = float(value)
        if not math.isfinite(number): raise ValueError('Non-finite JSON number')
        return number
    try: return json.loads(data, parse_constant=invalid, parse_float=finite)
    except RecursionError as error: raise ValueError('JSON nesting too deep') from error


def request(url: str, params: Mapping[str, Any]) -> dict[str, Any]:
    validate_url(url)
    req = Request(url + '?' + urlencode(params), headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    deadline = time.monotonic() + 15
    for attempt in range(2):
        try:
            with build_opener(SafeRedirect()).open(req, timeout=min(8, max(0.1, deadline-time.monotonic()))) as response:
                chunks, count = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise NetworkError('Weather request deadline exceeded')
                    chunk = response.read(min(16384, LIMIT+1-count))
                    if not chunk:
                        break
                    chunks.append(chunk); count += len(chunk)
                    if count > LIMIT:
                        raise ValueError('Weather response too large')
                result = strict_json(b''.join(chunks))
            if not isinstance(result, dict) or result.get('error'):
                raise ValueError('Invalid weather response')
            return result
        except HTTPError as exc:
            try:
                delay = max(0, min(900, int(exc.headers.get('Retry-After', '1'))))
            except (TypeError, ValueError):
                try: delay = max(0, min(900, int((parsedate_to_datetime(exc.headers['Retry-After'])-datetime.now(timezone.utc)).total_seconds())))
                except (KeyError, TypeError, ValueError): delay = 60
            exc.close()
            if attempt == 0 and exc.code in (429, 500, 502, 503, 504) and delay <= 2 and time.monotonic()+delay+3 < deadline:
                time.sleep(delay)
                continue
            raise NetworkError('Provider rate limit' if exc.code == 429 else 'Weather HTTP error', delay) from exc
        except (URLError, TimeoutError) as exc:
            raise NetworkError('Weather connection unavailable') from exc
    raise NetworkError('Weather connection unavailable')
