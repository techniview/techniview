import json
from dataclasses import dataclass

from ..models import ExecutionMode, Problem, ProblemTestCase


@dataclass(frozen=True)
class CaseExecution:
    source_code: str
    stdin: str | None
    expected_output: str


def _normalized_json(value: str) -> str:
    try:
        return json.dumps(json.loads(value), separators=(",", ":"), sort_keys=True)
    except json.JSONDecodeError:
        return value


def build_case_execution(
    problem: Problem,
    test_case: ProblemTestCase,
    source_code: str,
) -> CaseExecution:
    if problem.execution_mode == ExecutionMode.STDIN_STDOUT:
        return CaseExecution(
            source_code=source_code,
            stdin=test_case.input,
            expected_output=test_case.expected_output,
        )

    serialized_input = repr(test_case.input)
    function_name = repr(problem.function_name)
    harness = f"""

import json as __techniview_json
__techniview_args = __techniview_json.loads({serialized_input})
__techniview_name = {function_name}
if "Solution" in globals():
    __techniview_target = getattr(Solution(), __techniview_name)
else:
    __techniview_target = globals()[__techniview_name]
if not isinstance(__techniview_args, list):
    __techniview_args = [__techniview_args]
__techniview_result = __techniview_target(*__techniview_args)
print(__techniview_json.dumps(
    __techniview_result, separators=(",", ":"), sort_keys=True
))
"""
    return CaseExecution(
        source_code=source_code + harness,
        stdin=None,
        expected_output=_normalized_json(test_case.expected_output),
    )
