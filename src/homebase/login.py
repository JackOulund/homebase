import time
from collections import deque
from html import escape
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from homebase.oauth import HomebaseOAuthProvider, LoginTransaction
from homebase.password import verify_password
from homebase.settings import Settings

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>homebase sign-in</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 22rem; margin: 4rem auto; padding: 0 1rem; }}
input, button {{ font-size: 1rem; padding: 0.6rem; width: 100%; box-sizing: border-box; margin-top: 0.5rem; }}
.error {{ color: #b00020; }}
.note {{ color: #555; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>homebase</h1>
{body}
</body>
</html>"""

FORM = """<p><strong>{client_name}</strong> wants access to your home tasks.
After signing in you are sent back to <strong>{redirect_host}</strong>.</p>
<p class="note">Only continue if you started connecting from Claude yourself just now.</p>
{error}
<form method="post" action="/login">
<input type="hidden" name="txn" value="{transaction_id}">
<label for="password">Password</label>
<input id="password" type="password" name="password" autocomplete="current-password" autofocus required>
<button type="submit">Sign in</button>
</form>"""


class LoginThrottle:
    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._failures: deque[float] = deque()

    def is_locked(self) -> bool:
        cutoff = time.monotonic() - self._window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return len(self._failures) >= self._max_failures

    def record_failure(self) -> None:
        self._failures.append(time.monotonic())


class LoginPage:
    def __init__(
        self,
        provider: HomebaseOAuthProvider,
        settings: Settings,
        throttle: LoginThrottle,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._throttle = throttle

    async def handle(self, request: Request) -> Response:
        if request.method == "POST":
            form = await request.form()
            return self._sign_in(
                str(form.get("txn", "")), str(form.get("password", ""))
            )
        return self._show(request.query_params.get("txn", ""))

    def _show(self, transaction_id: str) -> Response:
        transaction = self._provider.find_login_transaction(transaction_id)
        if transaction is None:
            return self._expired()
        return self._form(transaction_id, transaction, status_code=200)

    def _sign_in(self, transaction_id: str, password: str) -> Response:
        transaction = self._provider.find_login_transaction(transaction_id)
        if transaction is None:
            return self._expired()
        if self._throttle.is_locked():
            return self._message(
                "Too many wrong attempts. Wait 15 minutes and try again.",
                status_code=429,
            )
        if not verify_password(password, self._settings.login_password_hash):
            self._throttle.record_failure()
            return self._form(
                transaction_id, transaction, status_code=401, error="Wrong password."
            )
        return RedirectResponse(
            self._provider.complete_login(transaction_id),
            status_code=302,
            headers=SECURITY_HEADERS,
        )

    def _form(
        self,
        transaction_id: str,
        transaction: LoginTransaction,
        status_code: int,
        error: str = "",
    ) -> Response:
        body = FORM.format(
            client_name=escape(transaction.client.client_name or "An application"),
            redirect_host=escape(urlparse(str(transaction.params.redirect_uri)).netloc),
            transaction_id=escape(transaction_id, quote=True),
            error=f'<p class="error">{escape(error)}</p>' if error else "",
        )
        return HTMLResponse(
            PAGE.format(body=body), status_code=status_code, headers=SECURITY_HEADERS
        )

    def _expired(self) -> Response:
        return self._message(
            "This sign-in link is no longer valid. Start connecting from Claude again.",
            status_code=400,
        )

    def _message(self, text: str, status_code: int) -> Response:
        return HTMLResponse(
            PAGE.format(body=f"<p>{escape(text)}</p>"),
            status_code=status_code,
            headers=SECURITY_HEADERS,
        )
