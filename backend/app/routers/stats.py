from fastapi import APIRouter

router = APIRouter(prefix="/stats", tags=["stats"])

# TODO: wire to MySQL analytics tables (submissions, attempts, class enrollments)
# TODO: add auth dependency - require student/teacher role


@router.get("/me")
def my_stats():
    # TODO: solved count, attempts, time/memory curves
    # TODO: query submissions WHERE user_id = current_user
    return {"message": "TODO: student stats from MySQL"}


@router.get("/class/{class_id}")
def class_stats(class_id: str):
    # TODO: TLE rate, WA breakdown, avg attempts
    # TODO: GROUP BY problem_id, status_id
    return {"message": f"TODO: class {class_id} stats from MySQL"}


# TODO: GET class problem failures
# TODO: GET leaderboard, optional
