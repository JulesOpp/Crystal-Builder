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


def index() -> Path | None:
    """The manual's front page, or None when there is none to open."""
    for parts in (BUNDLED, CHECKOUT):
        page = root().joinpath(*parts, "index.html")
        if page.is_file():
            return page
    return None
