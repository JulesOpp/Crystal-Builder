"""How many workers ``-n auto`` starts: as many as the machine can hold.

xdist's own answer is one per core.  On an 8 GB M2 that is eight
workers of up to a gigabyte each, and the run that followed swapped
until it stalled: thirty minutes and not finished at three workers,
with every small file read queued behind the swap.  So ``auto`` is the
smaller of what the memory and the fast cores allow -- see
``tests/conftest.py``.
"""

import pytest

from tests import conftest

GB = 2**30


@pytest.mark.parametrize("cores, memory, expected", [
    (4, 8 * GB, 2),        # an 8 GB M2: the memory decides
    (8, 16 * GB, 7),       # one fast core left for the person
    (10, 32 * GB, 9),
    (12, 64 * GB, 11),     # plenty of memory: the cores decide
    (8, 4 * GB, 1),        # never none
    (1, 32 * GB, 1),
])
def test_auto_is_the_smaller_of_what_memory_and_cores_allow(
        cores, memory, expected):
    assert conftest.auto_workers(cores, memory) == expected


def test_with_the_memory_unknown_the_cores_decide():
    assert conftest.auto_workers(6, None) == 5


def test_a_number_in_the_environment_wins(monkeypatch):
    monkeypatch.setenv("XTAL_TEST_WORKERS", "3")
    assert conftest.pytest_xdist_auto_num_workers(config=None) == 3


def test_auto_asks_this_machine(monkeypatch):
    monkeypatch.delenv("XTAL_TEST_WORKERS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(conftest, "_fast_cores", lambda: 4)
    monkeypatch.setattr(conftest, "_memory", lambda: 8 * GB)
    assert conftest.pytest_xdist_auto_num_workers(config=None) == 2


def test_ci_keeps_one_worker_a_core(monkeypatch):
    """A CI runner has nobody to leave a core for and nothing else to
    leave memory to, so it keeps xdist's own answer, as it had."""
    monkeypatch.delenv("XTAL_TEST_WORKERS", raising=False)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(conftest.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(conftest, "_memory", lambda: 8 * GB)
    assert conftest.pytest_xdist_auto_num_workers(config=None) == 4
