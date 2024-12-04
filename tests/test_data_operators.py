import pytest
from utils.data_operators import flatten_list


def test_flatten_list_with_nested_lists():
    # Test with a deeply nested list
    nested_list = [1, [2, [3, [4, [5]]]]]
    result = flatten_list(nested_list)
    assert result == [1, 2, 3, 4, 5]


def test_flatten_list_with_empty_list():
    # Test with an empty list
    nested_list = []
    result = flatten_list(nested_list)
    assert result == []


def test_flatten_list_with_mixed_data_types():
    # Test with mixed data types
    nested_list = [1, "string", [3.14, ["nested", [True]]]]
    result = flatten_list(nested_list)
    assert result == [1, "string", 3.14, "nested", True]


def test_flatten_list_with_single_level_list():
    # Test with a single-level list
    nested_list = [1, 2, 3, 4]
    result = flatten_list(nested_list)
    assert result == [1, 2, 3, 4]


def test_flatten_list_with_list_of_empty_lists():
    # Test with a list containing empty lists
    nested_list = [[], [[]], [[[]]], 1, [2]]
    result = flatten_list(nested_list)
    assert result == [1, 2]


def test_flatten_list_with_no_lists():
    # Test with a non-nested list (already flattened)
    nested_list = [1, 2, 3]
    result = flatten_list(nested_list)
    assert result == [1, 2, 3]


def test_flatten_list_with_large_nested_list():
    # Test with a large nested list
    nested_list = [i for i in range(1000)] + [[i for i in range(1000, 2000)]]
    result = flatten_list(nested_list)
    assert result == [i for i in range(2000)]
