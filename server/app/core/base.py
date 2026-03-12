from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PDABaseModel(BaseModel):
    """Shared model base so all contracts behave consistently."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
        use_enum_values=False,
    )
