import ast
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def build_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate a basic arithmetic expression (+, -, *, /, parentheses).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Arithmetic expression, e.g. (12+8)/2",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "utc_time",
                "description": "Get the current UTC timestamp in ISO format.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def safe_eval_math(expression: str) -> float:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
        ast.Constant,
    )

    def _eval(node: ast.AST) -> float:
        if not isinstance(node, allowed_nodes):
            raise ValueError("Unsupported operation")
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("Division by zero")
                return left / right
        raise ValueError("Invalid expression")

    parsed = ast.parse(expression, mode="eval")
    return _eval(parsed)


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    if tool_name == "calculator":
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            return "calculator error: missing expression"
        try:
            value = safe_eval_math(expression)
            return f"calculator result: {value}"
        except Exception as exc:
            return f"calculator error: {exc}"

    if tool_name == "utc_time":
        return f"current utc time: {datetime.now(timezone.utc).isoformat()}"

    return f"unsupported tool: {tool_name}"


def extract_tool_call(assistant_message: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    tool_calls = assistant_message.get("tool_calls")
    if not tool_calls:
        return None

    first_call = tool_calls[0]
    function_call = first_call.get("function", {})
    name = function_call.get("name")
    raw_arguments = function_call.get("arguments", "{}")
    if not name:
        return None
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return name, arguments
