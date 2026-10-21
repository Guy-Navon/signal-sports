"""Keep verification tokens and OAuth callback secrets out of access logs.

The verification link carries its token in the URL fragment, which browsers
never send, and the API receives tokens only in POST bodies, which are not
logged. This filter is the backstop for a token that arrives in a query
string anyway (a mangled or hand-edited link), so it cannot land in the
uvicorn access log. The explicit development mailer (MAIL_BACKEND=console)
logs through its own logger, which this filter is not attached to.
"""

from __future__ import annotations

import logging
import re

# t/token: email-verification links. code/state: the Google callback
# (/api/auth/google/callback?code=…&state=…), which arrives as a GET and so
# lands in the access log; both are single use, but they are still secrets.
_SECRET_PARAM = re.compile(r"([?&#;](?:t|token|code|state)=)[^&#\s\"']+", re.IGNORECASE)
REDACTED = "[redacted]"


def redact(text: str) -> str:
    return _SECRET_PARAM.sub(lambda m: m.group(1) + REDACTED, text)


class SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def install_access_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        target = logging.getLogger(name)
        if not any(isinstance(f, SecretRedactingFilter) for f in target.filters):
            target.addFilter(SecretRedactingFilter())
