"""The command every "not installed" hint gives.

It used to be ``pip install 'crystal-builder[x]'`` everywhere, and the
first person to follow the ORB engine's copy of it got ``does not
provide the extra 'orb'`` and nothing installed, while the panel went
on saying ORB was not installed.  See :mod:`xtal.install`.
"""

import io
import sys
import tokenize
from pathlib import Path

from xtal import install

ROOT = Path(__file__).resolve().parents[1]


def test_the_command_is_this_interpreter_s_pip():
    """A bare ``pip`` is whichever is first on the PATH, and a package
    it installs lands where this Python never looks."""
    assert install.command("orb").startswith(
        f'"{sys.executable}" -m pip install')


def test_a_checkout_installs_the_extra_from_itself():
    """Installing the checkout rewrites the metadata that names the
    extras, so an extra added since the last install is found rather
    than refused."""
    root = install.checkout()

    assert root == ROOT
    assert install.command("orb").endswith(f'-e "{ROOT}[orb]"')


def test_an_installed_copy_names_the_package(monkeypatch):
    monkeypatch.setattr(install, "checkout", lambda: None)

    assert install.command("orb").endswith(
        'pip install "crystal-builder[orb]"')


def _string_literals(path):
    """Every string in the file that is not a docstring or comment."""
    tokens = tokenize.generate_tokens(
        io.StringIO(path.read_text(encoding="utf-8")).readline)
    previous = None
    for token in tokens:
        if token.type == tokenize.STRING:
            docstring = previous in (None, tokenize.INDENT,
                                     tokenize.NEWLINE, tokenize.NL,
                                     tokenize.DEDENT) \
                and token.string.lstrip("rbfuRBFU").startswith(
                    ('"""', "'''"))
            if not docstring:
                yield token.start[0], token.string
        if token.type not in (tokenize.COMMENT, tokenize.NL):
            previous = token.type


def test_no_hint_offers_the_shorthand_that_installs_nothing():
    """Every hint goes through :func:`xtal.install.command`.  A second
    spelling is how the Force Field panel and the Engines page came to
    give different commands for the same extra."""
    offenders = []
    for folder in ("xtal", "xtalapp"):
        for path in (ROOT / folder).rglob("*.py"):
            if "pormake" in path.parts or path.name == "install.py":
                continue
            for line, text in _string_literals(path):
                if "crystal-builder[" in text:
                    offenders.append(f"{path.relative_to(ROOT)}:{line}")

    assert offenders == []
