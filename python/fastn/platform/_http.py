# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Internal HTTP helpers for the transport: retry set, backoff, loose JSON parsing, error-message extraction.

A port of node/src/http.ts. Not part of the public surface.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from typing import Any, Dict, Mapping, Optional, Tuple

from ._version import VERSION

#: Answers worth one more try: rate limit and gateway errors.
RETRY_STATUS = frozenset({429, 502, 503, 504})

#: Waits between attempts; tests replace it with a no-op.
sleep = time.sleep


def backoff(attempt: int) -> float:
    """Exponential backoff with a cap and a little jitter: 0.5s, 1s, 2s, 4s, 8s (+ up to 200ms), in seconds."""
    return min(0.5 * float(2**attempt), 8.0) + random.random() * 0.2


def retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    """The wait before the next attempt: Retry-After when the answer carries one (capped at 30s), else backoff()."""
    raw = headers.get("retry-after")
    try:
        ra = float(raw) if raw is not None else float("nan")
    except (TypeError, ValueError):
        ra = float("nan")
    if math.isfinite(ra) and ra > 0:
        return min(ra, 30.0)
    return backoff(attempt)


def default_user_agent() -> str:
    return f"fastn-python-sdk/{VERSION}"


def merge_options(defaults: Optional[Mapping[str, Any]], opts: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per-call options over client defaults; `headers` merged, everything else overridden."""
    out: Dict[str, Any] = dict(defaults or {})
    out.update(opts or {})
    headers: Dict[str, str] = {}
    headers.update((defaults or {}).get("headers") or {})
    headers.update((opts or {}).get("headers") or {})
    out["headers"] = headers
    return out


def parse_loose(text: str, content_type: str = "") -> Any:
    """JSON when the body is JSON (by content type or by its first character), otherwise the text as is."""
    s = text.strip()
    if not s:
        return text
    if "json" in content_type or re.match(r"^[\[{]", s):
        try:
            return json.loads(s)
        except ValueError:
            pass
    return text


def error_info(body: Any, fallback: str = "") -> Tuple[str, Optional[Any], Any, bool]:
    """The message, code and details out of an error body, whichever of the API's shapes it has.

    Returns (message, code, details, has_details).
    """
    if isinstance(body, dict):
        e = body.get("error")
        nested = e if isinstance(e, dict) else None
        if isinstance(e, str):
            message: Any = e
        elif nested is not None and "message" in nested:
            message = nested.get("message")
        else:
            message = body.get("message", body.get("detail"))
        code = body.get("code")
        has_details = False
        details = None
        if nested is not None:
            if nested.get("code") is not None:
                code = nested.get("code")
            if "details" in nested:
                has_details, details = True, nested.get("details")
        if not isinstance(message, str):
            message = fallback or json.dumps(body, separators=(",", ":"))[:300]
        return message, code, details, has_details
    text = fallback or (body if isinstance(body, str) else ("" if body is None else str(body)))
    return str(text)[:300], None, None, False
