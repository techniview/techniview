from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..core.judge0 import judge0_submit
from ..models import (
    Difficulty,
    ExecutionMode,
    Problem,
    ProblemOrigin,
    ProblemState,
    ProblemTag,
    ProblemTestCase,
    QuestionSet,
    QuestionSetItem,
    QuestionSetState,
    TestVisibility,
    UserRole,
)
from ..services.execution import build_case_execution
from .problems import _visible_problem

router = APIRouter(tags=["authoring"])


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str
    expected_output: str
    visibility: TestVisibility = TestVisibility.PUBLIC


class ProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1)
    difficulty: Difficulty
    execution_mode: ExecutionMode
    function_name: str = Field(min_length=1, max_length=255)
    starter_code: str
    canonical_solution: str | None = None
    cpu_time_limit_seconds: Decimal = Decimal("2.000")
    memory_limit_kb: int = 128000
    attribution: str | None = None
    license: str | None = None
    tags: list[str] = []
    test_cases: list[CaseInput] = []


class QuestionSetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None


class ItemsInput(BaseModel):
    problem_ids: list[int]


def _professor(user):
    if user.role != UserRole.PROFESSOR:
        raise ApiError(403, "professor_required", "Professor access is required.")


def _load_problem(db, pid):
    obj = db.scalar(
        select(Problem)
        .options(selectinload(Problem.tags), selectinload(Problem.test_cases))
        .where(Problem.id == pid)
    )
    if not obj:
        raise ApiError(404, "problem_not_found", "Problem not found.")
    return obj


def _owned_draft(problem, user):
    if problem.owner_id != user.id or problem.origin != ProblemOrigin.CUSTOM:
        raise ApiError(404, "problem_not_found", "Problem not found.")
    if problem.state != ProblemState.DRAFT:
        raise ApiError(
            409, "problem_not_draft", "Published or archived problems cannot be edited."
        )


def _set_payload(db, problem, body):
    tags = (
        list(db.scalars(select(ProblemTag).where(ProblemTag.slug.in_(body.tags))).all())
        if body.tags
        else []
    )
    if len(tags) != len(set(body.tags)):
        raise ApiError(422, "invalid_tags", "One or more tags do not exist.")
    problem.title, problem.prompt = body.title, body.prompt
    problem.difficulty, problem.execution_mode = body.difficulty, body.execution_mode
    problem.function_name, problem.starter_code = body.function_name, body.starter_code
    problem.canonical_solution = body.canonical_solution
    problem.cpu_time_limit_seconds, problem.memory_limit_kb = (
        body.cpu_time_limit_seconds,
        body.memory_limit_kb,
    )
    problem.attribution, problem.license = body.attribution, body.license
    problem.tags = tags
    problem.test_cases.clear()
    db.flush()
    problem.test_cases.extend(
        ProblemTestCase(
            case_order=i,
            visibility=c.visibility,
            input=c.input,
            expected_output=c.expected_output,
        )
        for i, c in enumerate(body.test_cases, start=1)
    )


def _problem_view(p):
    return {
        "id": p.id,
        "title": p.title,
        "prompt": p.prompt,
        "difficulty": p.difficulty,
        "origin": p.origin,
        "state": p.state,
        "execution_mode": p.execution_mode,
        "function_name": p.function_name,
        "starter_code": p.starter_code,
        "cpu_time_limit_seconds": p.cpu_time_limit_seconds,
        "memory_limit_kb": p.memory_limit_kb,
        "tags": [t.slug for t in p.tags],
        "test_cases": [
            {
                "case_order": c.case_order,
                "input": c.input,
                "expected_output": c.expected_output,
                "visibility": c.visibility,
            }
            for c in p.test_cases
        ],
        "attribution": p.attribution,
        "license": p.license,
    }


def _qs(db, qid, user):
    q = db.scalar(
        select(QuestionSet)
        .options(
            selectinload(QuestionSet.items)
            .selectinload(QuestionSetItem.problem)
            .selectinload(Problem.tags)
        )
        .where(QuestionSet.id == qid, QuestionSet.owner_id == user.id)
    )
    if q is None:
        raise ApiError(404, "question_set_not_found", "Question set not found.")
    return q


def _qs_view(q):
    return {
        "id": q.id,
        "title": q.title,
        "description": q.description,
        "state": q.state,
        "items": [
            {
                "item_order": i.item_order,
                "problem": {
                    "id": i.problem.id,
                    "title": i.problem.title,
                    "difficulty": i.problem.difficulty,
                    "origin": i.problem.origin,
                    "state": i.problem.state,
                    "tags": [t.slug for t in i.problem.tags],
                },
            }
            for i in q.items
        ],
    }


@router.post("/problems", status_code=201)
def create_problem(body: ProblemInput, db: DbSession, user: CurrentUser):
    _professor(user)
    p = Problem(
        owner_id=user.id,
        origin=ProblemOrigin.CUSTOM,
        state=ProblemState.DRAFT,
        title=body.title,
        prompt=body.prompt,
        difficulty=body.difficulty,
        execution_mode=body.execution_mode,
        function_name=body.function_name,
        starter_code=body.starter_code,
    )
    db.add(p)
    _set_payload(db, p, body)
    db.commit()
    db.refresh(p)
    return _problem_view(_load_problem(db, p.id))


@router.patch("/problems/{problem_id}")
def update_problem(
    problem_id: int, body: ProblemInput, db: DbSession, user: CurrentUser
):
    _professor(user)
    p = _load_problem(db, problem_id)
    _owned_draft(p, user)
    _set_payload(db, p, body)
    db.commit()
    return _problem_view(_load_problem(db, p.id))


@router.post("/problems/{problem_id}/copy", status_code=201)
def copy_problem(problem_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    src = _visible_problem(db, problem_id, user)
    p = Problem(
        owner_id=user.id,
        copied_from_id=src.id,
        origin=ProblemOrigin.CUSTOM,
        state=ProblemState.DRAFT,
        title=src.title,
        prompt=src.prompt,
        difficulty=src.difficulty,
        execution_mode=src.execution_mode,
        function_name=src.function_name,
        starter_code=src.starter_code,
        canonical_solution=src.canonical_solution,
        cpu_time_limit_seconds=src.cpu_time_limit_seconds,
        memory_limit_kb=src.memory_limit_kb,
        attribution=src.attribution,
        license=src.license,
        tags=list(src.tags),
    )
    p.test_cases = [
        ProblemTestCase(
            case_order=c.case_order,
            visibility=c.visibility,
            input=c.input,
            expected_output=c.expected_output,
        )
        for c in src.test_cases
    ]
    db.add(p)
    db.commit()
    db.refresh(p)
    return _problem_view(_load_problem(db, p.id))


@router.post("/problems/{problem_id}/validate")
def validate_problem(problem_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    p = _load_problem(db, problem_id)
    _owned_draft(p, user)
    issues = []
    if not p.title.strip() or not p.prompt.strip():
        issues.append("title and prompt are required")
    if not p.function_name.isidentifier():
        issues.append("function_name must be a valid identifier")
    if p.cpu_time_limit_seconds <= 0 or p.memory_limit_kb <= 0:
        issues.append("resource limits must be positive")
    if not p.test_cases:
        issues.append("at least one test case is required")
    if not p.canonical_solution:
        issues.append("canonical_solution is required")
    if p.canonical_solution and p.test_cases and not issues:
        for case in p.test_cases:
            execution = build_case_execution(p, case, p.canonical_solution)
            try:
                result = judge0_submit(
                    execution.source_code,
                    stdin=execution.stdin,
                    expected_output=execution.expected_output,
                    wait=True,
                    timeout=10,
                    cpu_time_limit=float(p.cpu_time_limit_seconds),
                    memory_limit=p.memory_limit_kb,
                )
                if result.get("status", {}).get("id") != 3:
                    issues.append(
                        f"canonical solution failed test case {case.case_order}"
                    )
            except Exception:
                issues.append(
                    f"canonical solution could not run test case {case.case_order}"
                )
    return {"valid": not issues, "issues": issues}


@router.post("/problems/{problem_id}/publish")
def publish_problem(problem_id: int, db: DbSession, user: CurrentUser):
    result = validate_problem(problem_id, db, user)
    if not result["valid"]:
        raise ApiError(
            422,
            "problem_invalid",
            "Problem must pass validation before publication.",
            details={"issues": result["issues"]},
        )
    p = _load_problem(db, problem_id)
    p.state = ProblemState.PUBLISHED
    db.commit()
    return _problem_view(p)


@router.post("/problems/{problem_id}/archive")
def archive_problem(problem_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    p = _load_problem(db, problem_id)
    if p.owner_id != user.id:
        raise ApiError(404, "problem_not_found", "Problem not found.")
    p.state = ProblemState.ARCHIVED
    db.commit()
    return _problem_view(p)


@router.get("/question-sets")
def list_question_sets(db: DbSession, user: CurrentUser):
    _professor(user)
    return {
        "items": [
            _qs_view(q)
            for q in db.scalars(
                select(QuestionSet)
                .options(
                    selectinload(QuestionSet.items)
                    .selectinload(QuestionSetItem.problem)
                    .selectinload(Problem.tags)
                )
                .where(QuestionSet.owner_id == user.id)
                .order_by(QuestionSet.id)
            ).all()
        ]
    }


@router.post("/question-sets", status_code=201)
def create_question_set(body: QuestionSetInput, db: DbSession, user: CurrentUser):
    _professor(user)
    q = QuestionSet(
        owner_id=user.id,
        title=body.title,
        description=body.description,
        state=QuestionSetState.DRAFT,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _qs_view(_qs(db, q.id, user))


@router.get("/question-sets/{question_set_id}")
def get_question_set(question_set_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    return _qs_view(_qs(db, question_set_id, user))


@router.patch("/question-sets/{question_set_id}")
def update_question_set(
    question_set_id: int, body: QuestionSetInput, db: DbSession, user: CurrentUser
):
    _professor(user)
    q = _qs(db, question_set_id, user)
    if q.state != QuestionSetState.DRAFT:
        raise ApiError(
            409,
            "question_set_not_draft",
            "Published or archived question sets cannot be edited.",
        )
    q.title = body.title
    q.description = body.description
    db.commit()
    return _qs_view(_qs(db, q.id, user))


@router.put("/question-sets/{question_set_id}/items")
def replace_items(
    question_set_id: int, body: ItemsInput, db: DbSession, user: CurrentUser
):
    _professor(user)
    q = _qs(db, question_set_id, user)
    if q.state != QuestionSetState.DRAFT:
        raise ApiError(
            409,
            "question_set_not_draft",
            "Published or archived question sets cannot be edited.",
        )
    if len(body.problem_ids) != len(set(body.problem_ids)):
        raise ApiError(
            422, "duplicate_problem", "Question sets cannot repeat a problem."
        )
    ps = (
        list(db.scalars(select(Problem).where(Problem.id.in_(body.problem_ids))).all())
        if body.problem_ids
        else []
    )
    if len(ps) != len(body.problem_ids) or any(
        not (
            (p.owner_id == user.id and p.origin == ProblemOrigin.CUSTOM)
            or (p.owner_id is None and p.state == ProblemState.PUBLISHED)
        )
        for p in ps
    ):
        raise ApiError(
            404, "problem_not_found", "One or more problems are unavailable."
        )
    q.items.clear()
    db.flush()
    q.items.extend(
        QuestionSetItem(item_order=i, problem_id=pid)
        for i, pid in enumerate(body.problem_ids, start=1)
    )
    db.commit()
    return _qs_view(_qs(db, q.id, user))


@router.post("/question-sets/{question_set_id}/publish")
def publish_question_set(question_set_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    q = _qs(db, question_set_id, user)
    if not q.items:
        raise ApiError(
            422, "empty_question_set", "Question set must contain at least one problem."
        )
    unpublished = [
        item.problem.id
        for item in q.items
        if item.problem.state != ProblemState.PUBLISHED
    ]
    if unpublished:
        raise ApiError(
            422,
            "unpublished_problems",
            "Every problem in a question set must be published first.",
            details={"problem_ids": unpublished},
        )
    q.state = QuestionSetState.PUBLISHED
    db.commit()
    return _qs_view(_qs(db, q.id, user))


@router.post("/question-sets/{question_set_id}/archive")
def archive_question_set(question_set_id: int, db: DbSession, user: CurrentUser):
    _professor(user)
    q = _qs(db, question_set_id, user)
    q.state = QuestionSetState.ARCHIVED
    db.commit()
    return _qs_view(q)
