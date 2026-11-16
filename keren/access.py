"""Demo access scope.

DEMO ONLY: the operator identity comes from a CLI flag and grants are hardcoded.
Production: operator identity comes from a verified OIDC/JWT token and the
manager->customer entitlement is looked up server-side. In both cases the
customerId is NEVER taken from model output; it is bound in code before any
tool runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DEMO_GRANTS = {"demo-pm": frozenset({"C-1042"})}
DEFAULT_OPERATOR = "demo-pm"
_ID_RE = re.compile(r"^C-\d{4}$")


class AccessDenied(Exception):
    """Same message for malformed/unknown/unauthorized, so IDs can't be probed."""

    def __init__(self) -> None:
        super().__init__("Access denied: customer not available in your scope.")


@dataclass(frozen=True)
class AuthorizedCustomer:
    """Proof of authorization. Create only via authorize(); tools require it."""

    operator: str
    customer_id: str


def authorize(operator: str, customer_id: str) -> AuthorizedCustomer:
    cid = customer_id.strip() if isinstance(customer_id, str) else ""
    if not _ID_RE.match(cid) or cid not in DEMO_GRANTS.get(operator, frozenset()):
        raise AccessDenied()
    return AuthorizedCustomer(operator=operator, customer_id=cid)
