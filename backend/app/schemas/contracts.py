from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ..models import (
    AssignmentState,
    Difficulty,
    ExecutionMode,
    MembershipRole,
    ProblemOrigin,
    ProblemState,
    UserRole,
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: UserRole


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    timezone: str
    archived_at: datetime | None
    membership_role: MembershipRole


class MemberResponse(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: MembershipRole
    joined_at: datetime
    withdrawn_at: datetime | None


class CourseListResponse(BaseModel):
    items: list[CourseResponse]
    total: int
    limit: int
    offset: int


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
    total: int
    limit: int
    offset: int


class PublicTestCaseResponse(BaseModel):
    id: int
    case_order: int
    input: str
    expected_output: str


class ProblemSummaryResponse(BaseModel):
    id: int
    title: str
    difficulty: Difficulty
    origin: ProblemOrigin
    state: ProblemState
    tags: list[str]


class ProblemDetailResponse(ProblemSummaryResponse):
    prompt: str
    execution_mode: ExecutionMode
    function_name: str
    starter_code: str
    public_tests: list[PublicTestCaseResponse]
    test_count: int
    attribution: str | None
    license: str | None


class ProblemListResponse(BaseModel):
    items: list[ProblemSummaryResponse]
    total: int
    limit: int
    offset: int


class CurriculumNodeResponse(BaseModel):
    problem: ProblemSummaryResponse
    priority: int
    prerequisite_problem_ids: list[int]
    status: str


class AssignmentItemResponse(BaseModel):
    id: int
    item_order: int
    points: Decimal
    submission_limit: int | None
    problem: ProblemSummaryResponse


class AssignmentResponse(BaseModel):
    id: int
    course_id: int
    title: str
    description: str | None
    state: AssignmentState
    available_at: datetime | None
    due_at: datetime | None
    created_at: datetime
    items: list[AssignmentItemResponse]


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    limit: int
    offset: int


class ErrorCounts(BaseModel):
    wrong_answer: int = 0
    compile_error: int = 0
    runtime_error: int = 0
    timeout: int = 0
    resource_limit: int = 0


class AnalyticsMetrics(BaseModel):
    assigned_count: int
    started_count: int
    completed_count: int
    completion_rate: float | None
    avg_completion_seconds: float | None
    median_completion_seconds: float | None
    total_valid_attempts: int
    total_retries: int
    avg_retries_per_student: float | None
    errors: ErrorCounts


class ProblemAnalyticsResponse(BaseModel):
    problem: ProblemSummaryResponse
    metrics: AnalyticsMetrics


class StudentProblemAnalyticsResponse(BaseModel):
    student: UserResponse
    problem: ProblemSummaryResponse
    metrics: AnalyticsMetrics


class AnalyticsOverviewResponse(BaseModel):
    summary: AnalyticsMetrics
    items: list[ProblemAnalyticsResponse]
    total: int
    limit: int
    offset: int


class AnalyticsFilters(BaseModel):
    difficulty: Difficulty | None
    tag: str | None


class StudentAnalyticsResponse(BaseModel):
    metrics: AnalyticsMetrics
    filters: AnalyticsFilters
