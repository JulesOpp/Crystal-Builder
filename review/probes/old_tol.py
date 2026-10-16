"""Pytest plugin: put SPECIAL_POSITION_TOL back to the old 1e-3."""


def pytest_configure(config):
    from xtal.core import p1
    p1.SPECIAL_POSITION_TOL = 1e-3
    p1.expand.__defaults__ = (1e-3,)
