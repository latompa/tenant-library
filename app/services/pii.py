"""PII hashing and masking utilities."""

import hashlib
import hmac

from app.config import settings


def hash_pii(value: str) -> str:
    """Irreversibly hash a PII value using HMAC-SHA256 with a server secret."""
    normalized = value.strip().lower()
    return hmac.new(
        settings.PII_HASH_SECRET.encode(),
        normalized.encode(),
        hashlib.sha256,
    ).hexdigest()


def mask_email(email: str) -> str:
    """Mask email: 'john.doe@example.com' -> 'j******e@e*****e.com'"""
    local, domain = email.split("@")
    domain_parts = domain.split(".")

    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

    domain_name = domain_parts[0]
    if len(domain_name) <= 2:
        masked_domain = domain_name[0] + "*"
    else:
        masked_domain = domain_name[0] + "*" * (len(domain_name) - 2) + domain_name[-1]

    tld = ".".join(domain_parts[1:])
    return f"{masked_local}@{masked_domain}.{tld}"


def mask_name(name: str) -> str:
    """Mask name: 'John Doe' -> 'J*** D**'"""
    parts = name.split()
    masked = []
    for part in parts:
        if not part:
            continue
        if len(part) == 1:
            masked.append(part[0])
        else:
            masked.append(part[0] + "*" * (len(part) - 1))
    return " ".join(masked)
