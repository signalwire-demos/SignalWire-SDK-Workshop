from swaig_cases import CASES, expect_ok


def test_cases_cover_core_workshop_functions():
    names = {c["function"] for c in CASES}
    assert {"tell_joke", "get_weather"} <= names


def test_each_case_has_args_and_string_expectation():
    for c in CASES:
        assert "function" in c and isinstance(c["args"], dict)
        assert isinstance(c["expect"], str)


def test_expect_ok_substring_match():
    assert expect_ok("Weather in Denver: Sunny", "Denver") is True
    assert expect_ok("error", "Denver") is False
    assert expect_ok("anything", "") is True   # empty needle = any text ok
