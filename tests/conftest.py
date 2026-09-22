"""Shared pytest config (B0). Tallies failures caused by NotImplementedError separately, so
a handoff can say "N not implemented (expected: lane not landed), M real failures"."""

from __future__ import annotations

_tally = {"not_implemented": [], "failed": [], "error": []}


def pytest_runtest_logreport(report):
    if report.when == "call" and report.failed:
        text = str(report.longrepr)
        key = "not_implemented" if "NotImplementedError" in text else "failed"
        _tally[key].append(report.nodeid)
    elif report.when in ("setup", "teardown") and report.failed:
        _tally["error"].append(report.nodeid)


def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    tr.write_sep("=", "Noteguard lane tally")
    tr.write_line(f"not implemented (lane not landed yet): {len(_tally['not_implemented'])}")
    tr.write_line(f"REAL failures: {len(_tally['failed'])}")
    for n in _tally["failed"]:
        tr.write_line(f"  FAILED {n}")
    tr.write_line(f"setup/teardown errors: {len(_tally['error'])}")
    for n in _tally["error"]:
        tr.write_line(f"  ERROR {n}")
