"""Hồi quy oracle logits; không thay đổi tolerance của campaign gốc."""
import numpy as np
import pytest

from fp32_reference import ATOL, RTOL, compare_logits


def test_tolerance_and_element_count():
    expected = np.array([[0.0, 10.0], [-10.0, 1.0]], dtype=np.float32)
    actual = expected + (ATOL + RTOL * np.abs(expected)) * 0.5
    result = compare_logits(actual, expected)
    assert result["failed_elements"] == 0 and result["elements"] == 4


@pytest.mark.parametrize("kind", ["outside", "position", "shape", "nan", "inf"])
def test_compare_rejects_invalid_logits(kind):
    expected = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    actual = expected.copy()
    if kind == "outside":
        actual[0, 0] += 3 * ATOL
    elif kind == "position":
        actual = actual[::-1]
    elif kind == "shape":
        actual = actual[:1]
    else:
        actual[0, 0] = {"nan": np.nan, "inf": np.inf}[kind]
    with pytest.raises(ValueError):
        compare_logits(actual, expected)
