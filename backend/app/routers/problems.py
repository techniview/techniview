from fastapi import APIRouter

router = APIRouter(prefix="/problems", tags=["problems"])

# TODO: import DB session / models when MySQL schema is ready
# TODO: load Code-Contests-Plus problems from MySQL (dedupe, validated via Judge0)
# TODO: add filtering by topic/difficulty for student view
# TODO: add pagination (limit/offset) for dashboard


@router.get("")
@router.get("/")
def list_problems():
    # TODO: query MySQL `problems` table, return list
    return {"message": "TODO: return problems from MySQL", "problems": []}


@router.get("/{problem_id}")
def get_problem(problem_id: int):
    # TODO: fetch one problem, hide expected_output
    return {"message": f"TODO: return problem {problem_id}"}


# TODO: POST /problems (teacher: create custom problem)
# TODO: PUT /problems/{id} (teacher: edit problem)
