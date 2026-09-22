from ..models import Assignment, Problem, TestVisibility


def problem_summary(problem: Problem) -> dict:
    return {
        "id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "origin": problem.origin,
        "state": problem.state,
        "tags": sorted(tag.slug for tag in problem.tags),
    }


def problem_detail(problem: Problem) -> dict:
    return {
        **problem_summary(problem),
        "prompt": problem.prompt,
        "execution_mode": problem.execution_mode,
        "function_name": problem.function_name,
        "starter_code": problem.starter_code,
        "public_tests": [
            {
                "id": case.id,
                "case_order": case.case_order,
                "input": case.input,
                "expected_output": case.expected_output,
            }
            for case in problem.test_cases
            if case.visibility == TestVisibility.PUBLIC
        ],
        "test_count": len(problem.test_cases),
        "attribution": problem.attribution,
        "license": problem.license,
    }


def assignment_response(assignment: Assignment) -> dict:
    return {
        "id": assignment.id,
        "course_id": assignment.course_id,
        "title": assignment.title,
        "description": assignment.description,
        "state": assignment.state,
        "available_at": assignment.available_at,
        "due_at": assignment.due_at,
        "created_at": assignment.created_at,
        "items": [
            {
                "id": item.id,
                "item_order": item.item_order,
                "points": item.points,
                "submission_limit": item.submission_limit,
                "problem": problem_summary(item.problem),
            }
            for item in assignment.items
        ],
    }
