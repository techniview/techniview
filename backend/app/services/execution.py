import ast
import json
from dataclasses import dataclass

from ..models import ExecutionMode, Problem, ProblemTestCase, SubmissionCaseResult


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


def _tree_arguments(problem: Problem) -> list[int]:
    """Read the input contract from the stored starter, not student annotations."""
    starter = getattr(problem, "starter_code", "") or ""
    try:
        module = ast.parse(starter)
    except SyntaxError:
        return []
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == problem.function_name:
            arguments = [arg for arg in node.args.args if arg.arg != "self"]
            return [
                index
                for index, argument in enumerate(arguments)
                if argument.annotation is not None
                and any(
                    isinstance(part, ast.Name) and part.id == "TreeNode"
                    for part in ast.walk(argument.annotation)
                )
            ]
    return []


def build_case_execution(
    problem: Problem,
    test_case: ProblemTestCase,
    source_code: str,
) -> CaseExecution:
    if problem.execution_mode == ExecutionMode.STDIN_STDOUT:
        return CaseExecution(
            source_code=f"{source_code.rstrip()}\n\n{problem.function_name}()\n",
            stdin=test_case.input,
            expected_output=test_case.expected_output,
        )

    linked_list_problem = any(
        tag.slug == "linked-list" for tag in getattr(problem, "tags", ())
    )
    tree_arguments = _tree_arguments(problem)
    tree_problem = bool(tree_arguments) or "TreeNode" in (
        getattr(problem, "starter_code", "") or ""
    )
    tree_prelude = (
        f"""
from typing import *
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
exec(compile({source_code!r}, "<student-submission>", "exec"), globals(), globals())
"""
        if tree_problem
        else ""
    )
    linked_list_prelude = (
        f"""
from typing import *

class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.data = val
        self.next = next

    @property
    def __next__(self):
        return self.next

    @__next__.setter
    def __next__(self, value):
        self.next = value
exec(compile({source_code!r}, "<student-submission>", "exec"), globals(), globals())
"""
        if linked_list_problem
        else ""
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
if {tree_problem!r}:
    def __techniview_make_tree(values):
        if not values or values[0] is None:
            return None
        root = TreeNode(values[0])
        queue = [root]
        cursor = 1
        for node in queue:
            for side in ("left", "right"):
                if cursor >= len(values):
                    break
                value = values[cursor]
                cursor += 1
                if value is not None:
                    child = TreeNode(value)
                    setattr(node, side, child)
                    queue.append(child)
        return root
    for __techniview_index in {tree_arguments!r}:
        __techniview_args[__techniview_index] = __techniview_make_tree(
            __techniview_args[__techniview_index]
        )
if {linked_list_problem!r}:
    def __techniview_make_list(values, cycle_at=-1):
        if not values:
            return None
        __techniview_nodes = [ListNode(value) for value in values]
        for __techniview_left, __techniview_right in zip(
            __techniview_nodes, __techniview_nodes[1:]
        ):
            __techniview_left.next = __techniview_right
        if 0 <= cycle_at < len(__techniview_nodes):
            __techniview_nodes[-1].next = __techniview_nodes[cycle_at]
        return __techniview_nodes[0]

    if __techniview_name == "hasCycle" and len(__techniview_args) == 2:
        __techniview_args = [
            __techniview_make_list(__techniview_args[0], __techniview_args[1])
        ]
    else:
        __techniview_args = [
            __techniview_make_list(__techniview_arg)
            if isinstance(__techniview_arg, list)
            else __techniview_arg
            for __techniview_arg in __techniview_args
        ]
__techniview_result = __techniview_target(*__techniview_args)
if {tree_problem!r} and isinstance(__techniview_result, TreeNode):
    __techniview_queue = [__techniview_result]
    __techniview_values = []
    for __techniview_node in __techniview_queue:
        if __techniview_node is None:
            __techniview_values.append(None)
            continue
        __techniview_values.append(__techniview_node.val)
        __techniview_queue.extend([
            __techniview_node.left, __techniview_node.right
        ])
    while __techniview_values and __techniview_values[-1] is None:
        __techniview_values.pop()
    __techniview_result = __techniview_values
if {linked_list_problem!r}:
    if __techniview_result is None and __techniview_name == "reorderList":
        __techniview_result = __techniview_args[0]
    if __techniview_result is None:
        __techniview_result = []
    if isinstance(__techniview_result, ListNode):
        __techniview_values = []
        __techniview_seen = set()
        while (
            __techniview_result is not None
            and id(__techniview_result) not in __techniview_seen
        ):
            __techniview_seen.add(id(__techniview_result))
            __techniview_values.append(__techniview_result.val)
            __techniview_result = __techniview_result.next
        __techniview_result = __techniview_values
print(__techniview_json.dumps(
    __techniview_result, separators=(",", ":"), sort_keys=True
))
"""
    return CaseExecution(
        source_code=(tree_prelude or linked_list_prelude or source_code) + harness,
        stdin=None,
        expected_output=_normalized_json(test_case.expected_output),
    )


_SHARED_SCRIPT_HEAD = """
import contextlib as __tv_contextlib
import io as __tv_io
import json as __tv_json
import os as __tv_os
import sys as __tv_sys
import traceback as __tv_traceback

class __tv_LimitedWriter(__tv_io.StringIO):
    def __init__(self, byte_limit):
        super().__init__()
        self.byte_limit = byte_limit
        self.byte_count = 0

    def write(self, value):
        size = len(value.encode("utf-8", errors="replace"))
        if self.byte_count + size > self.byte_limit:
            raise OSError("case output limit exceeded")
        self.byte_count += size
        return super().write(value)

__tv_protocol = __tv_os.fdopen(__tv_os.dup(1), "w", encoding="utf-8", buffering=1)
__tv_module = {"__name__": "__main__"}
__tv_start_stdout = __tv_LimitedWriter(1048576)
__tv_start_stderr = __tv_LimitedWriter(1048576)
__tv_start_error = None
try:
    with (
        __tv_contextlib.redirect_stdout(__tv_start_stdout),
        __tv_contextlib.redirect_stderr(__tv_start_stderr),
    ):
        exec(compile(__tv_source, "<student-submission>", "exec"),
             __tv_module, __tv_module)
except Exception as __tv_error:
    __tv_start_error = type(__tv_error).__name__
    __tv_start_stderr.write(__tv_traceback.format_exc()[-8192:])
"""

_SHARED_SCRIPT_TAIL = """
for __tv_index in range(__tv_case_count):
    __tv_line = __tv_sys.stdin.readline()
    if not __tv_line:
        break
    __tv_request = __tv_json.loads(__tv_line)
    if __tv_request.get("index") != __tv_index:
        break
    __tv_limit = __tv_request["output_limit_bytes"]
    __tv_out = __tv_LimitedWriter(__tv_limit)
    __tv_err = __tv_LimitedWriter(__tv_limit)
    __tv_exception = None
    __tv_output_exceeded = False
    if __tv_index == 0:
        __tv_out.write(__tv_start_stdout.getvalue())
        __tv_err.write(__tv_start_stderr.getvalue())
    if __tv_start_error is not None:
        __tv_exception = __tv_start_error
    else:
        try:
            __tv_input = __tv_request["input"]
            with (
                __tv_contextlib.redirect_stdout(__tv_out),
                __tv_contextlib.redirect_stderr(__tv_err),
            ):
                if __tv_mode == "call":
                    __tv_namespace = __tv_module.copy()
                    __tv_namespace["__tv_input"] = __tv_input
                    exec(compile(__tv_harnesses[__tv_index], "<case-harness>", "exec"),
                         __tv_namespace, __tv_namespace)
                else:
                    __tv_previous_stdin = __tv_sys.stdin
                    try:
                        __tv_sys.stdin = __tv_io.StringIO(__tv_input)
                        __tv_module[__tv_entry]()
                    finally:
                        __tv_sys.stdin = __tv_previous_stdin
        except Exception as __tv_error:
            __tv_exception = type(__tv_error).__name__
            __tv_output_exceeded = (
                isinstance(__tv_error, OSError)
                and str(__tv_error) == "case output limit exceeded"
            )
            try:
                __tv_err.write(__tv_traceback.format_exc()[-8192:])
            except OSError:
                __tv_output_exceeded = True
    __tv_protocol.write(__tv_json.dumps({
        "index": __tv_index,
        "stdout": __tv_out.getvalue(),
        "stderr": __tv_err.getvalue(),
        "exception": __tv_exception,
        "output_exceeded": __tv_output_exceeded,
    }, separators=(",", ":")) + "\\n")
    __tv_protocol.flush()
    if __tv_start_error is not None:
        break
"""


def build_shared_execution(
    problem: Problem, cases: list[SubmissionCaseResult], source_code: str
) -> str:
    """Build one interpreter with externally supplied case inputs and no answers."""
    if not cases:
        raise ValueError("shared execution requires cases")
    if problem.execution_mode == ExecutionMode.STDIN_STDOUT:
        prefix = source_code
        harnesses: list[str] = []
        mode = "stdin"
    else:
        marker = "\n\nimport json as __techniview_json\n"
        harnesses = []
        prefix = ""
        for index, case in enumerate(cases):
            execution = build_case_execution(problem, case, source_code)
            prepared_prefix, separator, harness = execution.source_code.partition(
                marker
            )
            if not separator or (index and prepared_prefix != prefix):
                raise ValueError("inconsistent prepared function harness")
            prefix = prepared_prefix
            old = f"__techniview_json.loads({case.input!r})"
            if harness.count(old) != 1:
                raise ValueError("case input placeholder not found")
            harnesses.append(
                (marker + harness).replace(
                    old, "__techniview_json.loads(__tv_input)", 1
                )
            )
        mode = "call"
    bindings = (
        f"__tv_source = {prefix!r}\n"
        f"__tv_harnesses = {harnesses!r}\n"
        f"__tv_case_count = {len(cases)}\n"
        f"__tv_mode = {mode!r}\n"
        f"__tv_entry = {problem.function_name!r}\n"
    )
    return bindings + _SHARED_SCRIPT_HEAD + _SHARED_SCRIPT_TAIL


def snapshot_case_result(
    problem: Problem, case: ProblemTestCase, source_code: str, **values
) -> SubmissionCaseResult:
    execution = build_case_execution(problem, case, source_code)
    return SubmissionCaseResult(
        test_case_id=case.id,
        case_order=case.case_order,
        visibility=case.visibility,
        input=case.input,
        expected_output=case.expected_output,
        execution_source=execution.source_code,
        execution_stdin=execution.stdin,
        execution_expected_output=execution.expected_output,
        cpu_time_limit_seconds=problem.cpu_time_limit_seconds,
        memory_limit_kb=problem.memory_limit_kb,
        **values,
    )
