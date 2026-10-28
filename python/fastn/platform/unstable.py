"""Internals with no compatibility promise: the wire manifest (`OPS`), the httpx transport and their types. They can
change in any release. Use them for debugging or to build your own transport, not in application code."""

from ._generated.ops import OPS
from ._transport import BodyDef, HttpxTransport, OpDef, ParamDef

__all__ = ["OPS", "BodyDef", "HttpxTransport", "OpDef", "ParamDef"]
