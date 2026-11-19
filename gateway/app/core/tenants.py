import re
from dataclasses import dataclass, field
from datetime import datetime

TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
DEFAULT_MODELS = ["auto", "mock-echo"]


class TenantExists(Exception):
    pass


class TenantNotFound(Exception):
    pass


@dataclass
class Tenant:
    id: str
    name: str
    allowed_models: list[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    active: bool = True

    def allows(self, model: str) -> bool:
        return "*" in self.allowed_models or model in self.allowed_models


@dataclass
class ApiKeyRecord:
    id: str
    tenant_id: str
    prefix: str
    created_at: datetime