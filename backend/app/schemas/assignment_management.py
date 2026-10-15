from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssignmentItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: int = Field(gt=0)
    points: Decimal = Field(default=Decimal("1"), gt=0, max_digits=10, decimal_places=4)
    submission_limit: int | None = Field(default=None, gt=0)


class AssignmentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    available_at: datetime | None = None
    due_at: datetime | None = None
    items: list[AssignmentItemInput] | None = Field(
        default=None, min_length=1, max_length=150
    )
    recipient_mode: Literal["all", "selected"] | None = None
    selected_membership_ids: list[int] | None = Field(default=None, max_length=2000)

    @field_validator("available_at", "due_at")
    @classmethod
    def normalize_timestamp(cls, value):
        return (
            value.astimezone(UTC).replace(tzinfo=None)
            if value and value.tzinfo
            else value
        )

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value.strip() if value is not None else value

    @model_validator(mode="after")
    def validate_nulls(self):
        for name in ("title", "items", "recipient_mode", "selected_membership_ids"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class AssignmentCreate(AssignmentEdit):
    title: str = Field(min_length=1, max_length=150)
    question_set_id: int | None = Field(default=None, gt=0)
    recipient_mode: Literal["all", "selected"] = "all"
    selected_membership_ids: list[int] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def source(self):
        if (self.question_set_id is None) == (self.items is None):
            raise ValueError("provide either question_set_id or items")
        return self


class RecipientChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    add_membership_ids: list[int] = Field(default_factory=list, max_length=2000)
    remove_membership_ids: list[int] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def disjoint(self):
        if set(self.add_membership_ids) & set(self.remove_membership_ids):
            raise ValueError("cannot add and remove the same recipient")
        return self
