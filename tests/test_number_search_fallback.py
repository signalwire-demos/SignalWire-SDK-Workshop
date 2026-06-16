"""Area-code search must auto-broaden to any US number when the requested area
code is out of stock, so the wizard never dead-ends (Chicago 312 is chronically
empty). Verified live: areacode=312 -> 0, no-areacode -> results."""
from python.provisioning import search_available_with_fallback


def _fake(in_stock):
    # returns a searcher: area_code in `in_stock` -> 1 number; else [];
    # None (no area code) -> a broadened result
    def search(creds, area_code, limit):
        if area_code is None:
            return [{"phone_number": "+12086239392", "region": "ID"}]
        return [{"phone_number": f"+1{area_code}5550100", "region": "X"}] if area_code in in_stock else []
    return search


def test_in_stock_area_code_no_fallback():
    nums, fell = search_available_with_fallback({}, "253", 8, _search=_fake({"253"}))
    assert fell is False and len(nums) == 1 and nums[0]["phone_number"].startswith("+1253")


def test_out_of_stock_area_code_broadens():
    nums, fell = search_available_with_fallback({}, "312", 8, _search=_fake({"253"}))
    assert fell is True and len(nums) == 1 and nums[0]["region"] == "ID"


def test_no_area_code_no_fallback_flag():
    nums, fell = search_available_with_fallback({}, None, 8, _search=_fake(set()))
    assert fell is False and len(nums) == 1


def test_broaden_also_empty_returns_empty_not_fellback():
    def empty(creds, ac, limit):
        return []
    nums, fell = search_available_with_fallback({}, "312", 8, _search=empty)
    assert nums == [] and fell is False
