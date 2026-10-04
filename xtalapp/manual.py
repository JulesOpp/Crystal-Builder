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


def page(name: str) -> Path | None:
    """One page of the manual, ``frameworks/carbon`` say, or None."""
    for parts in (BUNDLED, CHECKOUT):
        path = root().joinpath(*parts, f"{name}.html")
        if path.is_file():
            return path
    return None


def add_help_button(buttons, name: str) -> None:
    """A Help button on a dialog's button box, opening the manual page
    that describes it.

    Help ▸ User Manual opens the front page, and from a builder's
    dialog that is a search away from what was wanted.  Greyed, with
    the reason, in a checkout whose manual has not been built.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QDialogButtonBox

    button = buttons.addButton(QDialogButtonBox.Help)
    found = page(name)
    if found is None:
        button.setEnabled(False)
        button.setToolTip(MISSING)
        return
    button.setToolTip(f"Open the manual's page on this ({name})")
    # Help's role would make the box emit helpRequested and nothing
    # else; a click is all this needs, and it must not close the
    # dialog.
    button.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(found))))
