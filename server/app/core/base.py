from __future__ import annotations

from pydantic import BaseModel


class PDABaseModel(BaseModel):
    """Shared model base so all contracts behave consistently."""

    class Config:
        extra = "forbid"
        validate_assignment = True
        allow_population_by_field_name = True
        use_enum_values = False
