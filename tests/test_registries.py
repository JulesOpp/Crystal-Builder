"""Engines, modules and formats are one kind of registry.

They were three copies of thirty lines, drifted: only modules could be
unregistered, formats had no ``names`` or ``len``, and an unknown
format did not say what there was instead.
"""

from types import SimpleNamespace

import pytest

from xtal.ff import ENGINES
from xtal.io import FORMATS
from xtal.modules import MODULES

REGISTRIES = {"engines": ENGINES, "modules": MODULES, "formats": FORMATS}


@pytest.mark.parametrize("name", sorted(REGISTRIES))
def test_every_registry_can_forget_what_it_was_given(name):
    """A registry that can only grow leaks between test cases, and a
    plugin that fails half way has to take back what it added."""
    registry = REGISTRIES[name]
    before = len(registry)
    item = SimpleNamespace(name="_passing_through", label="Passing",
                           order=999)

    registry.register(item)
    assert "_passing_through" in registry
    assert "_passing_through" in registry.names()
    registry.unregister("_passing_through")

    assert "_passing_through" not in registry
    assert len(registry) == before


@pytest.mark.parametrize("name", sorted(REGISTRIES))
def test_an_unknown_name_says_what_there_is(name):
    registry = REGISTRIES[name]
    with pytest.raises(ValueError) as refused:
        registry.get("nonesuch")
    assert registry.names()[0] in str(refused.value)


def test_formats_keep_the_order_they_were_registered_in():
    """That is the order a file dialog lists them in; engines and
    modules are the ones sorted, by their place in a chooser."""
    assert FORMATS.names()[0] == "cif"
    assert ENGINES.names()[0] == "uff"
