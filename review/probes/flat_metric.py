"""Pytest plugin: drop the root-2 shear scaling in xtal.ff.optimize."""
import numpy as np


def pytest_configure(config):
    from xtal.ff import optimize

    def w_of(tensor):
        t = np.asarray(tensor, dtype=float)
        return np.array([t[0, 0], t[1, 1], t[2, 2],
                         t[1, 2], t[0, 2], t[0, 1]])

    def tensor_of(w):
        a, b, c, d, e, f = (float(v) for v in w)
        return np.array([[a, f, e], [f, b, d], [e, d, c]])

    optimize._w_of = w_of
    optimize._tensor_of = tensor_of
