"""Pytest plugin: take the site projectors' tolerance back to 1e-6."""


def pytest_configure(config):
    from xtal.core import p1
    p1.SPECIAL_POSITION_TOL = 1e-6
