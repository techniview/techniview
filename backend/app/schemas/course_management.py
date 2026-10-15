from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class CourseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=10000)
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank.")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown timezone.") from exc
        return value


class CourseUpdateRequest(CourseCreateRequest):
    pass


class CsvEnrollmentRequest(BaseModel):
    csv: str = Field(min_length=1, max_length=500000)


class PasswordRecoveryRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=1024)
    password_confirm: str = Field(min_length=8, max_length=1024)


class EmailVerificationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
