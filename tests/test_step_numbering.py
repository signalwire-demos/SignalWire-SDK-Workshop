# tests/test_step_numbering.py
"""The visible 'Version N' labels must read 1..7 contiguously even though the
route/file names (/step04, step06_*) keep their historical numbers. Guards
against the workshop-floor confusion where the list jumped '4' -> '6' (raised
by Nicholas Ahrendt). 'Version' is the product's chosen word (matches the
frontend STEPS_META and README); the 3-step setup wizard's 'Step N of 3' is a
separate flow."""
import re
from main import STEPS


def test_version_labels_are_contiguous_1_to_7():
    nums = []
    for entry in STEPS:
        desc = entry[2]  # (route, agent_class, desc)
        m = re.search(r"Version\s+(\d+)", desc)
        assert m, f"no 'Version N' in label: {desc!r}"
        nums.append(int(m.group(1)))
    assert nums == [1, 2, 3, 4, 5, 6, 7], nums


def test_routes_unchanged():
    routes = [entry[0] for entry in STEPS]
    assert routes == ["/step04", "/step06", "/step07", "/step08",
                      "/step09", "/step10", "/step11"]
