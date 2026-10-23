"""Typed Arena API errors."""

from __future__ import annotations


class ArenaError(Exception):
    code = "ARENA_ERROR"
    http_status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ArenaError):
    code = "NOT_FOUND"
    http_status = 404


class UnauthorizedError(ArenaError):
    code = "UNAUTHORIZED"
    http_status = 401


class ForbiddenError(ArenaError):
    code = "FORBIDDEN"
    http_status = 403


class LockPassedError(ArenaError):
    code = "LOCK_PASSED"
    http_status = 409


class ConflictError(ArenaError):
    code = "CONFLICT"
    http_status = 409


class ValidationError(ArenaError):
    code = "VALIDATION"
    http_status = 422
