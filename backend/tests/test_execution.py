import json
import subprocess
import sys
from types import SimpleNamespace

from app.models import ExecutionMode
from app.services.execution import build_case_execution


def test_stdin_stdout_execution_calls_the_problem_function():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.STDIN_STDOUT,
        function_name="solve",
    )
    test_case = SimpleNamespace(input="4 5\n", expected_output="9\n")

    execution = build_case_execution(problem, test_case, "def solve():\n    pass\n")

    assert execution.source_code.endswith("solve()\n")
    assert execution.stdin == "4 5\n"
    assert execution.expected_output == "9\n"


def test_call_based_execution_keeps_function_harness():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
    )
    test_case = SimpleNamespace(input="[4, 5]", expected_output="9")

    execution = build_case_execution(
        problem, test_case, "def solve(a, b):\n    return a+b"
    )

    assert "__techniview_target(*__techniview_args)" in execution.source_code
    assert execution.stdin is None
    assert execution.expected_output == "9"


def _run_case(problem, arguments, source):
    execution = build_case_execution(
        problem,
        SimpleNamespace(input=json.dumps(arguments), expected_output="null"),
        source,
    )
    result = subprocess.run(
        [sys.executable, "-c", execution.source_code],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    return json.loads(result.stdout)


def test_tree_input_uses_stored_contract_when_student_omits_annotations():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        starter_code="def solve(root: Optional[TreeNode], values: List[int]): pass",
        tags=[],
    )
    result = _run_case(
        problem,
        [[1, None, 2, 3], [9, 8]],
        "def solve(root, values):\n"
        "    return [root.val, root.right.left.val, values]\n",
    )
    assert result == [1, 3, [9, 8]]
    assert _run_case(problem, [[], []], "def solve(root, values): return root") is None


def test_tree_output_serializes_sparse_tree_without_converting_array_arguments():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="build",
        starter_code="def build(values: List[int]) -> Optional[TreeNode]: pass",
        tags=[],
    )
    assert _run_case(
        problem,
        [[1, 2, 3]],
        "def build(values):\n"
        "    child = TreeNode(values[1], TreeNode(values[2]))\n"
        "    return TreeNode(values[0], None, child)",
    ) == [1, None, 2, 3]
    assert _run_case(
        problem,
        [[1]],
        "def build(values): return TreeNode(values[0], TreeNode(2))",
    ) == [1, 2]
    assert _run_case(
        problem,
        [[1]],
        "def build(values):\n"
        "    root = TreeNode(1)\n"
        "    root.left = TreeNode(2, None, TreeNode(3))\n"
        "    return root",
    ) == [1, 2, None, None, 3]


def test_empty_in_place_linked_list_returns_empty_array():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="reorderList",
        tags=[SimpleNamespace(slug="linked-list")],
    )
    assert _run_case(problem, [[]], "def reorderList(head): pass") == []
