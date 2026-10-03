"""Where the user manual is, for *Help > User Manual*.

The manual is ``docs/manual``, built by Sphinx into HTML.  A packaged
build carries that HTML in ``manual/`` beside the package
(``packaging/bundle.py`` puts it there, and ``--selftest`` fails a
build without it); a checkout has it wherever the manual's own
command left it, ``build/manual/html``.  Both are found from the
package's parent, as the samples are, so neither needs a
``sys.frozen`` branch.

It opens in the browser rather than in a window of ours: the pages
are a website, with a search box, a contents sidebar and links out,
and a browser is what reads one.
"""

from __future__ import annotations

from pathlib import Path

#: In a packaged build, relative to :func:`root`.
BUNDLED = ("manual",)
#: In a checkout, where the command below writes it.
CHECKOUT = ("build", "manual", "html")

#: The manual CI job's own command.
BUILD = "sphinx-build -b html docs/manual build/manual/html"

MISSING = (f"The user manual has not been built in this checkout: "
           f"{BUILD} (with the docs extra installed) builds it.")


def root() -> Path:
    """The folder the package sits in: the checkout, or the unpacked
    bundle."""
    return Path(__file__).resolve().parent.parent


#: The third-party notices, by name: at the bundle's root, or where
#: ``scripts/third_party_notices.py`` writes them in a checkout.
NOTICES = "THIRD_PARTY_NOTICES.md"


def notices() -> Path | None:
    """The third-party notices Help > About links, or None in a
    checkout that has not written them."""
    for parts in ((NOTICES,), ("build", NOTICES)):
        path = root().joinpath(*parts)
        if path.is_file():
            return path
    return None


def index() -> Path | None:
    """The manual's front page, or None when there is none to open."""
    for parts in (BUNDLED, CHECKOUT):
        page = root().joinpath(*parts, "index.html")
        if page.is_file():
            return page
    return None
