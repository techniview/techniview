import ast
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
