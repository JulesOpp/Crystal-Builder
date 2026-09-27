"""
xtal.agent -- Crystal Builder driven by an AI assistant, or a script.

One surface: a :class:`Session` holds a structure and its undo stack
and changes it only through verbs, each of them the command the window
pushes for the same gesture.  Every verb answers with a
:class:`VerbResult`; :func:`inspect` says what a structure is and what
is wrong with it; :func:`render` draws it; :func:`capabilities` says
what this install can run.  Findings are :class:`Diagnostic` objects
with closed codes, each carrying its remedy.

The protocol an assistant should follow is ``skill/SKILL.md``, shipped
beside this file -- ``xtal skill install`` puts it where Claude Code
reads it.

Headless: nothing here imports Qt.  :func:`render` needs VTK (the
``gui`` extra) and runs it in a subprocess.
"""

from xtal.agent.answers import Inspection, VerbResult
from xtal.agent.capabilities import capabilities, help_for
from xtal.agent.diagnostics import CODES, Diagnostic
from xtal.agent.inspect import inspect
from xtal.agent.render import render
from xtal.agent.session import BuildFailed, Session

__all__ = ["CODES", "BuildFailed", "Diagnostic", "Inspection",
           "Session", "VerbResult", "capabilities", "help_for",
           "inspect", "render"]
