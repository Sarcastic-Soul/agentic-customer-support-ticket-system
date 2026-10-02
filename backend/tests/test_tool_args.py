"""A malformed tool call comes back to the model as a fixable error - which
field, what was wrong, the schema to follow - not a crash or a vague string.
Pure: no DB, no LLM.
"""

from pydantic import ValidationError

import app.tools  # noqa: F401 - registers the tools
from app.tools.registry import get_tool_spec, invalid_arguments_result


def _error_for(tool: str, args: dict) -> dict:
    spec = get_tool_spec(tool)
    try:
        spec.args_schema.model_validate(args)
    except ValidationError as exc:
        return invalid_arguments_result(spec, exc)
    raise AssertionError("args were valid")


def test_missing_field_is_named():
    result = _error_for("request_refund", {"txn_ref": "TXN-1", "reason": "duplicate"})
    assert result["error"] == "invalid_arguments"
    assert [f["field"] for f in result["fields"]] == ["amount"]
    assert "amount" in result["expected_schema"]["properties"]
    assert "request_refund" in result["hint"]


def test_wrong_type_is_named():
    result = _error_for(
        "request_refund", {"txn_ref": "TXN-1", "amount": "a lot", "reason": "duplicate"}
    )
    assert result["fields"][0]["field"] == "amount"
    assert result["fields"][0]["problem"]


def test_string_amount_still_coerces():
    # Gemini sends Decimal fields as strings - that must keep validating.
    spec = get_tool_spec("request_refund")
    args = spec.args_schema.model_validate(
        {"txn_ref": "TXN-1", "amount": "499.00", "reason": "duplicate"}
    )
    assert str(args.amount) == "499.00"
