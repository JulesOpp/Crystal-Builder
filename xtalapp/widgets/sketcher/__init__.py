"""
xtalapp.widgets.sketcher
========================
The 2D chemical sketcher: a page a molecule is drawn on, and the tools
beside it.

The drawing is :class:`xtal.build.sketch.Sketch`, which holds no Qt;
:class:`~xtalapp.widgets.sketcher.canvas.SketchCanvas` paints it and
turns clicks and keys into its edits, and
:class:`~xtalapp.widgets.sketcher.tools.SketchTools` chooses what a
click does.  :class:`xtalapp.dialogs.sketch.SketchEditor` puts the two
together behind the ``set_smiles`` / ``smilesChanged`` contract every
dialog that draws a molecule already speaks.
"""

from xtalapp.widgets.sketcher.canvas import SketchCanvas
from xtalapp.widgets.sketcher.tools import SketchTools

__all__ = ["SketchCanvas", "SketchTools"]
