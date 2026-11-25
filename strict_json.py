"""Strict UTF-8 JSON loading for source-bound evidence and configuration files.

Python's standard JSON decoder silently accepts duplicate object names and keeps
the last value. It also accepts NaN and Infinity by default, although those
constants are outside the JSON specification. Very large valid exponents can
overflow Python floats to infinity, while tiny nonzero values can underflow to
zero. Evidence pipelines use this loader so accepted numbers remain in the supported finite range and every object has one unambiguous interpretation.
"""
import json
import math


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value):
    raise ValueError(f"Non-standard JSON numeric constant is not permitted: {value}")



def _finite_float(value):
    """Reject JSON float conversions that overflow or underflow."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"JSON floating-point number is outside the finite range: {value}"
        )
    mantissa = value.lower().split("e", 1)[0]
    if number == 0.0 and any(digit in mantissa for digit in "123456789"):
        raise ValueError(
            f"JSON floating-point number underflows to zero: {value}"
        )
    return number


def strict_json_loads(source):
    """Decode UTF-8 JSON while rejecting duplicate keys and lossy float ranges."""
    if isinstance(source, (bytes, bytearray)):
        source = bytes(source).decode("utf-8")
    elif not isinstance(source, str):
        raise TypeError("JSON input must be UTF-8 bytes or text")
    return json.loads(
        source,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonstandard_constant,
        parse_float=_finite_float,
    )
