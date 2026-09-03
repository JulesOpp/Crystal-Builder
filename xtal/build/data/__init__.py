"""The fragment library's data, as a package rather than a folder.

A package because that is what :mod:`importlib.resources` addresses:
``resources.files("xtal.build.data")`` finds the JSON in a wheel, in a
zip and in a source checkout without any of the three being a special
case, and ``Path(__file__).parent`` is right in only the last of them.
"""
