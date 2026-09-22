from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.db import SessionLocal
from .core.security import hash_password
from .models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    Course,
    CourseMembership,
    CurriculumEdge,
    CurriculumNode,
    Difficulty,
    ExecutionMode,
    MembershipRole,
    Problem,
    ProblemOrigin,
    ProblemState,
    ProblemTag,
    ProblemTestCase,
    StudentAssignmentProgress,
    StudentPracticeProgress,
    TestVisibility,
    User,
    UserRole,
)

DEMO_TEACHER_EMAIL = "teacher@techniview.local"
DEMO_STUDENT_EMAIL = "student@techniview.local"


def seed_demo(db: Session) -> None:
    if db.scalar(select(User).where(User.email == DEMO_TEACHER_EMAIL)) is not None:
        return

    teacher = User(
        name="Demo Professor",
        email=DEMO_TEACHER_EMAIL,
        password_hash=hash_password("teacher-demo"),
        role=UserRole.PROFESSOR,
    )
    student = User(
        name="Demo Student",
        email=DEMO_STUDENT_EMAIL,
        password_hash=hash_password("student-demo"),
        role=UserRole.STUDENT,
    )
    db.add_all([teacher, student])
    db.flush()

    loops = ProblemTag(name="Loops", slug="loops")
    arrays = ProblemTag(name="Arrays", slug="arrays")
    first = Problem(
        origin=ProblemOrigin.IMPORTED,
        state=ProblemState.PUBLISHED,
        title="Sum a List",
        prompt="Return the sum of the supplied integers.",
        difficulty=Difficulty.EASY,
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="sum_list",
        starter_code="def sum_list(values):\n    pass\n",
        source_dataset="demo",
        source_problem_id="sum-list",
        attribution="TechniView demonstration data",
        license="CC BY 4.0",
        tags=[arrays],
    )
    second = Problem(
        origin=ProblemOrigin.IMPORTED,
        state=ProblemState.PUBLISHED,
        title="Count Evens",
        prompt="Count the even integers in a list.",
        difficulty=Difficulty.MEDIUM,
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="count_evens",
        starter_code="def count_evens(values):\n    pass\n",
        source_dataset="demo",
        source_problem_id="count-evens",
        attribution="TechniView demonstration data",
        license="CC BY 4.0",
        tags=[arrays, loops],
    )
    db.add_all([first, second])
    db.flush()
    db.add_all(
        [
            ProblemTestCase(
                problem_id=first.id,
                case_order=1,
                visibility=TestVisibility.PUBLIC,
                input="[[1, 2, 3]]",
                expected_output="6",
            ),
            ProblemTestCase(
                problem_id=first.id,
                case_order=2,
                visibility=TestVisibility.HIDDEN,
                input="[[-2, 2]]",
                expected_output="0",
            ),
            ProblemTestCase(
                problem_id=second.id,
                case_order=1,
                visibility=TestVisibility.PUBLIC,
                input="[[1, 2, 4]]",
                expected_output="2",
            ),
        ]
    )
    db.add_all(
        [
            CurriculumNode(problem_id=first.id, priority=1),
            CurriculumNode(problem_id=second.id, priority=2),
        ]
    )
    db.flush()
    db.add(
        CurriculumEdge(
            prerequisite_problem_id=first.id,
            problem_id=second.id,
        )
    )

    course = Course(name="CS 101 Demo", description="Seeded development course")
    db.add(course)
    db.flush()
    instructor = CourseMembership(
        course_id=course.id,
        user_id=teacher.id,
        role=MembershipRole.INSTRUCTOR,
    )
    learner = CourseMembership(
        course_id=course.id,
        user_id=student.id,
        role=MembershipRole.STUDENT,
    )
    db.add_all([instructor, learner])
    db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    assignment = Assignment(
        course_id=course.id,
        assigned_by_membership_id=instructor.id,
        title="List Fundamentals",
        description="Practice list traversal and aggregation.",
        state=AssignmentState.PUBLISHED,
        available_at=now - timedelta(days=2),
        due_at=now + timedelta(days=5),
    )
    db.add(assignment)
    db.flush()
    first_item = AssignmentItem(
        assignment_id=assignment.id,
        problem_id=first.id,
        item_order=1,
        points=Decimal("10"),
    )
    second_item = AssignmentItem(
        assignment_id=assignment.id,
        problem_id=second.id,
        item_order=2,
        points=Decimal("10"),
    )
    db.add_all([first_item, second_item])
    db.flush()
    db.add(
        AssignmentRecipient(
            assignment_id=assignment.id,
            membership_id=learner.id,
            course_id=course.id,
        )
    )
    db.add_all(
        [
            StudentPracticeProgress(
                student_id=student.id,
                problem_id=first.id,
                first_opened_at=now - timedelta(minutes=12),
                first_passed_at=now - timedelta(minutes=4),
                best_score=Decimal("1"),
                valid_attempt_count=3,
                retry_count=2,
                wrong_answer_count=1,
                runtime_error_count=1,
                last_attempt_at=now - timedelta(minutes=4),
            ),
            StudentAssignmentProgress(
                student_id=student.id,
                assignment_item_id=first_item.id,
                first_opened_at=now - timedelta(hours=1),
                first_passed_at=now - timedelta(minutes=45),
                best_score=Decimal("1"),
                valid_attempt_count=2,
                retry_count=1,
                wrong_answer_count=1,
                last_attempt_at=now - timedelta(minutes=45),
            ),
        ]
    )
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_demo(db)


if __name__ == "__main__":
    main()
