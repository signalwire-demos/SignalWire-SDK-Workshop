"""Single source of truth for SWAIG function test cases.

Both the /admin "Run test" endpoint and scripts/swaig_preflight.py import CASES
so the dashboard and the CLI exercise the same inputs and expectations. As of
the server-side-weather change, every workshop SWAIG function runs in-process
(define_tool / SDK skill) — there is no serverless DataMap — so each case is
invoked the same way via agent._execute_swaig_function(...). Functions that have
no case here are still testable: the runner invokes them with empty args and no
expectation.
"""


def expect_ok(result_text, needle):
    return (needle or "").lower() in (result_text or "").lower()


CASES = [
    {"function": "tell_joke",   "args": {},                      "expect": ""},
    {"function": "get_weather", "args": {"city": "Chicago"},     "expect": "Chicago"},
    {"function": "calculate",   "args": {"expression": "2 + 2"}, "expect": "4"},
]
