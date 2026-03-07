from __future__ import annotations

from server.app.core import BJJRecordFields, ErrorCode


REQUIRED_BJJ_FIELDS = (
    "date",
    "position",
    "orientation",
    "distance",
    "goal",
    "your_action",
    "opponent_response",
)


def validate_bjj_record(record: BJJRecordFields) -> list[str]:
    errors: list[str] = []
    for field_name in REQUIRED_BJJ_FIELDS:
        value = getattr(record, field_name)
        if value in (None, ""):
            errors.append(f"{ErrorCode.MISSING_BJJ_REQUIRED_FIELD}:{field_name}")
    return errors
