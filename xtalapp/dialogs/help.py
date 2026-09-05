"""
xtalapp.dialogs.help
====================
Help generated from the application, not written beside it.

Every action already carries a ``tip=`` -- the sentence in the status
bar and the tooltip -- and every module parameter already carries a
``Param.help``.  Between them that is most of a manual, written by the
person who added each command, at the moment they added it.  Help
pages typed out separately would repeat all of it and then drift: a
command renamed, a parameter given a range, a module that stopped
shipping, and the prose still says what used to be true.

So both pages are read off the live objects at the moment the window
opens.  A command with no ``tip`` shows as a name and a shortcut and
nothing else, which is honest and is also the list of tips still owed.

**Only registry actions appear.**  The menu bar is walked for the
grouping -- a user looks for a command where they last saw it, so File
is the File section -- but an entry is kept only if it is one of
``window.actions_``.  That is the line between a command and a
document, and it draws itself: the recent files, the elements present,
the background swatches and the dock toggles are all built as bare
``QAction`` objects by the code that lists them, so none of them reach
the page.  The samples do, because each one *is* a registered action
carrying a sentence about the structure it opens, and that sentence is
help.

Anything in the registry that no menu reached is collected at the end
rather than dropped, because a command reachable only from a context
menu is exactly the one a user needs help finding.

Modeless, and kept alive by the window: help about the structure in
front of you should not be a modal sheet over the top of it.
"""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from xtal.modules import MODULES

#: Enough of a stylesheet for Qt's rich text, which is not a browser:
#: it has no ``border-collapse`` and no ``:nth-child``, so the tables
#: are drawn with cell padding and a header row and nothing else.
STYLE = """
<style>
 h2 { margin-top: 18px; }
 h3 { margin-top: 14px; margin-bottom: 2px; }
 td { padding-right: 14px; padding-bottom: 3px; }
 th { text-align: left; padding-right: 14px; }
 .key { color: #555; }
 .none { color: #888; font-style: italic; }
</style>
"""


def _clean(text: str) -> str:
    """A menu label as it is read, without the mnemonic ampersands."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def _tip(action) -> str:
    """The action's ``tip=``, or the empty string.

    ``QAction.toolTip`` falls back to the action's own text when
    nothing set one, so a command with no tip would otherwise show its
    own name a second time as its explanation.  Qt builds that
    fallback by dropping the mnemonic *and* the trailing ellipsis, so
    "&Open..." has to be compared as "Open" -- otherwise every command
    that opens a dialog is explained by its own name.
    """
    tip = action.toolTip()
    text = _clean(action.text())
    for tail in ("...", "\u2026"):
        text = text[:-len(tail)] if text.endswith(tail) else text
    return "" if tip in (text, _clean(action.text())) else tip


def _shortcut(action) -> str:
    """The first key bound to the action, spelled for this platform."""
    keys = action.shortcuts()
    return keys[0].toString() if keys else ""


def _registry_names(window) -> dict[int, str]:
    """``id(QAction) -> registry name``, for the menu walk."""
    return {id(window.actions_[name]): name
            for name in window.actions_.names()}


def _entries(menu, known, seen, prefix=""):
    """The registry actions under one menu, submenus included."""
    rows = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        if action.menu() is not None:
            rows += _entries(action.menu(), known, seen,
                             f"{prefix}{_clean(action.text())} ▸ ")
            continue
        name = known.get(id(action))
        if name is None or name in seen:
            continue
        seen.add(name)
        rows.append((prefix + _clean(action.text()),
                     _shortcut(action), _tip(action)))
    return rows


def command_sections(window) -> list[tuple[str, list[tuple]]]:
    """The commands, grouped the way the menu bar groups them.

    Each section is ``(title, [(label, shortcut, tip), ...])``.  A
    command is listed once, under the first menu that offered it: the
    boundary rules and the drawing styles are in the View menu and in
    the viewport's own context menu, and reading them twice would say
    nothing the first reading did not.
    """
    known = _registry_names(window)
    seen: set[str] = set()
    sections = []
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is None:
            continue
        rows = _entries(menu, known, seen)
        if rows:
            sections.append((_clean(action.text()), rows))

    rest = []
    for name in window.actions_.names():
        if name in seen:
            continue
        entry = window.actions_[name]
        rest.append((_clean(entry.text()), _shortcut(entry),
                     _tip(entry)))
    if rest:
        sections.append(("Elsewhere", rest))
    return sections


def commands_html(window) -> str:
    """Every command in the application, as one page."""
    out = [STYLE, "<h1>Commands</h1>",
           "<p>Every command, where the menu bar keeps it.  A command "
           "with no description here is one whose tip is still "
           "owed.</p>"]
    for title, rows in command_sections(window):
        out.append(f"<h2>{escape(title)}</h2>")
        out.append("<table width='100%'><tr><th>Command</th>"
                   "<th>Key</th><th>What it does</th></tr>")
        for label, key, tip in rows:
            out.append(
                f"<tr><td><b>{escape(label)}</b></td>"
                f"<td class='key'>{escape(key)}</td>"
                f"<td>{escape(tip)}</td></tr>")
        out.append("</table>")
    return "\n".join(out)


def _number(value) -> str:
    """A bound as a user reads it.

    ``%g`` is right for the tolerances and wrong for the counts: it
    turns a sample limit of a million into ``1e+06`` and a seed's
    ceiling into ``2.14748e+09``, neither of which is a number
    anybody recognises as the one they may type.
    """
    if float(value).is_integer():
        return f"{int(value):d}"
    return f"{value:g}"


def param_range(param) -> str:
    """What a parameter accepts, from its own declaration.

    The kind, the bounds and the default are three of the four things
    a user asks about a field they have never set; ``Param.help`` is
    the fourth and is written by hand beside it.
    """
    if param.kind == "choice":
        return "one of " + ", ".join(
            str(label) for _value, label in param.values_and_labels())
    low, high = param.minimum, param.maximum
    bits = [param.kind]
    if low is not None and high is not None:
        bits.append(f"{_number(low)} to {_number(high)}{param.suffix}")
    elif low is not None:
        bits.append(f"at least {_number(low)}{param.suffix}")
    elif high is not None:
        bits.append(f"at most {_number(high)}{param.suffix}")
    elif param.suffix:
        bits.append(f"in {param.suffix.strip()}")
    return ", ".join(bits)


def modules_html() -> str:
    """Every module, its actions and every value they ask for.

    Availability is asked for here as the Modules menu asks for it,
    because "what does this parameter mean" and "why can I not click
    this" are the same question at the moment somebody opens help.
    """
    out = [STYLE, "<h1>Modules</h1>",
           "<p>What each module runs, and what it asks for first.</p>"]
    for module in MODULES:
        out.append(f"<h2>{escape(module.label)}</h2>")
        if module.description:
            out.append(f"<p>{escape(module.description)}</p>")
        available = module.availability()
        if not available.ok:
            out.append(f"<p class='none'>Not available: "
                       f"{escape(available.reason)}</p>")
        for action in module.actions:
            out.append(f"<h3>{escape(_clean(action.label))}</h3>")
            if action.tip:
                out.append(f"<p>{escape(action.tip)}</p>")
            if not action.params:
                out.append("<p class='none'>No settings.</p>")
                continue
            out.append("<table width='100%'><tr><th>Setting</th>"
                       "<th>Accepts</th><th>Default</th>"
                       "<th>What it is</th></tr>")
            for param in action.params:
                out.append(
                    f"<tr><td><b>{escape(param.title)}</b></td>"
                    f"<td>{escape(param_range(param))}</td>"
                    f"<td>{escape(str(param.default_value()))}</td>"
                    f"<td>{escape(param.help)}</td></tr>")
            out.append("</table>")
    return "\n".join(out)


class HelpWindow(QDialog):
    """The two generated pages, side by side in a tab bar."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(760, 620)

        self.tabs = QTabWidget()
        self.pages = {}
        for title, text in (("Commands", commands_html(window)),
                            ("Modules", modules_html())):
            view = QTextBrowser()
            view.setOpenExternalLinks(True)
            view.setHtml(text)
            self.tabs.addTab(view, title)
            self.pages[title] = view

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)
