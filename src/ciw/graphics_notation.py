"""Bounded UV scalar notation compiled to typed data and safe GLSL expressions.

The grammar reuses the existing safe interpreter. Authored code never reaches a
Python evaluator or a shader directly: only allowlisted typed nodes are emitted.
"""
from __future__ import annotations

import ast
import io
import tokenize

from .control_contracts import keys, number
from .procedural_contract import FIELD_LIMIT, FUNCTIONS, evaluate, parse_expression

IR_SCHEMA = "ciw.graphics-scalar-ir.v1"


def validate_parameters(parameters):
    if type(parameters) is not dict or len(parameters) > 8 or {"u", "v"} & set(parameters):
        raise ValueError("Require at most eight parameters without reserved UV names")
    # Reuse the existing identifier profile without evaluating a field.
    parse_expression("0", parameters)
    for name, parameter in parameters.items():
        keys(parameter, {"value", "minimum", "maximum"})
        lo, hi, value = (number(parameter[key]) for key in ("minimum", "maximum", "value"))
        if not -FIELD_LIMIT <= lo <= value <= hi <= FIELD_LIMIT:
            raise ValueError("Declared parameter values must lie within their finite bounds")


def _translated(expression, parameters):
    validate_parameters(parameters)
    if type(expression) is not str or not expression.strip() or len(expression) > 1024:
        raise ValueError("UV notation must be bounded nonempty text")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(expression).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError("Invalid UV notation") from exc
    rewritten = []
    for token in tokens:
        if token.type == tokenize.NAME and token.string in {"x", "y", "z"}:
            raise ValueError("UV programs use u and v; Cartesian coordinate names are reserved")
        value = {"u": "x", "v": "y"}.get(token.string, token.string) if token.type == tokenize.NAME else token.string
        rewritten.append(token._replace(string=value))
    translated = tokenize.untokenize(rewritten)
    return translated, parse_expression(translated, parameters)


def compile_uv(expression: str, parameters: dict) -> dict:
    """Compile scalar notation to bounded inert typed-node JSON."""
    _text, tree = _translated(expression, parameters)

    def node(value):
        record = {"type": "scalar"}
        if type(value) is ast.Constant:
            return record | {"op": "constant", "value": float(value.value)}
        if type(value) is ast.Name:
            if value.id in {"x", "y"}:
                return record | {"op": "coordinate", "name": {"x": "u", "y": "v"}[value.id]}
            return record | {"op": "parameter", "name": value.id, "value": float(parameters[value.id]["value"])}
        if type(value) is ast.UnaryOp:
            return record | {"op": "neg" if type(value.op) is ast.USub else "pos", "operand": node(value.operand)}
        if type(value) is ast.BinOp:
            operation = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div", ast.Pow: "pow"}[type(value.op)]
            return record | {"op": operation, "left": node(value.left), "right": node(value.right)}
        return record | {"op": "call", "name": value.func.id, "arguments": [node(argument) for argument in value.args]}

    return {"schema": IR_SCHEMA, "coordinate_system": "uv", "scalar_type": "binary64",
            "expression": expression, "root": node(tree.body)}


def evaluate_uv(expression: str, parameters: dict, u, v):
    translated, _tree = _translated(expression, parameters)
    return evaluate(translated, parameters, u, v, 0.0)


def _literal(value):
    value = number(value)
    text = format(value, ".17g")
    return text if "." in text or "e" in text.lower() else text + ".0"


def glsl_expression(ir: dict, parameters: dict) -> str:
    """Translate only a freshly validated typed IR; no user shader text escapes."""
    from .operations.runner import digest
    if type(ir) is not dict or digest(ir) != digest(compile_uv(ir.get("expression"), parameters)):
        raise ValueError("Typed scalar IR differs from its declared safe notation")

    def emit(value):
        operation = value["op"]
        if operation in {"constant", "parameter"}:
            return _literal(value["value"])
        if operation == "coordinate":
            return value["name"]
        if operation in {"pos", "neg"}:
            return "(" + ("+" if operation == "pos" else "-") + emit(value["operand"]) + ")"
        if operation == "call":
            return value["name"] + "(" + ",".join(emit(argument) for argument in value["arguments"]) + ")"
        left, right = emit(value["left"]), emit(value["right"])
        if operation == "pow":
            # GLSL pow is undefined for negative bases even at integer powers.
            # Fixed helper calls preserve integer power semantics and avoid
            # exponential source expansion for nested bounded powers.
            return f"netPow{int(value['right']['value'])}({left})"
        return "(" + left + {"add": "+", "sub": "-", "mul": "*", "div": "/"}[operation] + right + ")"

    return emit(ir["root"])


GLSL_POWER_HELPERS = "\n".join(
    f"float netPow{exponent}(float t){{return " + ("1.0" if exponent == 0 else "*".join(["t"] * exponent)) + ";}"
    for exponent in range(7))
