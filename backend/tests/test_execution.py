import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.models import ExecutionMode
from app.services.execution import build_case_execution, build_shared_execution


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


def _shared_frames(problem, source, inputs):
    cases = [
        SimpleNamespace(input=value, expected_output="secret-answer-never-in-script")
        for value in inputs
    ]
    script = build_shared_execution(problem, cases, source)
    assert "secret-answer-never-in-script" not in script
    with subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        assert process.stdin is not None
        assert process.stdout is not None
        frames = []
        for index, value in enumerate(inputs):
            if process.poll() is not None or (frames and frames[-1] is None):
                frames.append(None)
                continue
            process.stdin.write(
                json.dumps({"index": index, "input": value, "output_limit_bytes": 4096})
                + "\n"
            )
            process.stdin.flush()
            line = process.stdout.readline()
            frames.append(json.loads(line) if line else None)
        process.stdin.close()
        process.wait(timeout=5)
        return frames, process.returncode


def test_shared_function_preserves_globals_but_creates_new_solution():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        tags=[],
        starter_code="def solve(value): pass",
    )
    source = (
        "counter = 0\n"
        "class Solution:\n"
        "    class_counter = 0\n"
        "    def __init__(self): self.instance_counter = 0\n"
        "    def solve(self, value):\n"
        "        global counter\n"
        "        counter += 1\n"
        "        Solution.class_counter += 1\n"
        "        self.instance_counter += 1\n"
        "        return [counter, Solution.class_counter, "
        "self.instance_counter, value]\n"
    )
    frames, code = _shared_frames(problem, source, ["[4]", "[5]"])
    assert code == 0
    assert [frame["stdout"] for frame in frames] == ["[1,1,1,4]\n", "[2,2,1,5]\n"]
    assert [frame["index"] for frame in frames] == [0, 1]


def test_shared_stdin_problem_keeps_module_state_and_resets_input():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.STDIN_STDOUT,
        function_name="solve",
    )
    source = (
        "import sys\ncount = 0\n"
        "def solve():\n"
        "    global count\n"
        "    count += 1\n"
        "    print(sys.stdin.read().strip(), count)\n"
    )
    frames, code = _shared_frames(problem, source, ["a\n", "b\n"])
    assert code == 0
    assert [frame["stdout"] for frame in frames] == ["a 1\n", "b 2\n"]


def test_shared_fatal_exit_leaves_later_case_without_frame():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        tags=[],
        starter_code="def solve(value): pass",
    )
    source = (
        "import os\n"
        "def solve(value):\n"
        "    if value == 2: os._exit(23)\n"
        "    return value\n"
    )
    frames, code = _shared_frames(problem, source, ["[1]", "[2]", "[3]"])
    assert code == 23
    assert frames[0]["stdout"] == "1\n"
    assert frames[1:] == [None, None]


def test_shared_process_background_thread_can_read_the_next_case():
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        starter_code="def solve(value): pass",
        tags=[],
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        leak_path = f"{temp_dir}/next-case"
        source = (
            "import os, sys, threading, time\n"
            "def steal_next_case():\n"
            f"    open({leak_path!r}, 'wb').write(os.read(0, 4096))\n"
            "class DelayedInput:\n"
            "    def readline(self):\n"
            "        time.sleep(0.1)\n"
            "        return ''\n"
            "def solve(value):\n"
            "    if value == 1:\n"
            "        threading.Thread(target=steal_next_case).start()\n"
            "        sys.stdin = DelayedInput()\n"
            "    return value\n"
        )
        cases = [
            SimpleNamespace(input=f"[{index}]", expected_output="unused")
            for index in (1, 2)
        ]
        script = build_shared_execution(problem, cases, source)
        with subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(
                json.dumps({"index": 0, "input": "[1]", "output_limit_bytes": 4096})
                + "\n"
            )
            process.stdin.flush()
            assert json.loads(process.stdout.readline())["stdout"] == "1\n"
            process.stdin.write(
                json.dumps(
                    {
                        "index": 1,
                        "input": "[987654]",
                        "output_limit_bytes": 4096,
                    }
                )
                + "\n"
            )
            process.stdin.close()
            process.wait(timeout=5)
        assert "987654" in Path(leak_path).read_text()
