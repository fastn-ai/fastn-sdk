# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Errors of the platform client: FastnApiError for every non-2xx answer, FastnNetworkError when nothing answered."""

from __future__ import annotations

from typing import Any, Optional


class FastnApiError(Exception):
    """Thrown for every non-2xx answer. `status`, `code` and `message` are what the API returned."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: Optional[str] = None,
        details: Any = None,
        method: str = "",
        path: str = "",
        request_id: Optional[str] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        #: HTTP status (0 when the request never reached the API).
        self.status = status
        #: API error code, e.g. NOT_FOUND, VALIDATION_ERROR, RATE_LIMITED, CONFLICT.
        self.code = code
        #: Extra details the API sent with the error, when any.
        self.details = details
        self.method = method
        self.path = path
        #: x-request-id of the failed call; quote it when reporting a problem to fastn.
        self.request_id = request_id
        #: The raw response body.
        self.body = body

    def __str__(self) -> str:
        return self.message

    @property
    def is_not_found(self) -> bool:
        return self.status == 404

    @property
    def is_conflict(self) -> bool:
        return self.status == 409

    @property
    def is_rate_limited(self) -> bool:
        return self.status == 429

    @property
    def is_auth(self) -> bool:
        return self.status in (401, 403)

    @property
    def is_validation(self) -> bool:
        return self.status in (400, 422)


class FastnNetworkError(Exception):
    """Thrown when the request could not be sent or timed out."""

    def __init__(self, message: str, method: str, path: str, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.method = method
        self.path = path
        self.cause = cause

    def __str__(self) -> str:
        return self.message
