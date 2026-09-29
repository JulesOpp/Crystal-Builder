"""
Blender's side of Export as STL: ``pdb_to_printable_stl.py`` with the
importer's centring declined, and otherwise exactly as its author
keeps it.

Atomic Blender draws a stick as instances aligned by the atom's
position with its component along the stick taken away, and divides
by the length of what is left -- zero whenever the stick's line runs
through the origin.  Its centring puts the cut's mean at the origin,
and a symmetric cell cut (MOF-5's) has sticks on lines through its
own middle, so the import raised ``ZeroDivisionError``.  The PDB is
written already centred, a small generic distance off the origin
(``xtal.modules.blender.OFF_CENTRE``), as the render's is; the
importer is only told not to undo that.

Loaded by path rather than imported, because Blender runs this file
with a Python that has no ``xtal``, and the vendored script's own
``__main__`` block is not run -- :func:`main` below is.
"""

import importlib.util
import os
import sys

import bpy

VENDORED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "pdb_to_printable_stl.py")

#: Every name the vendored script might give the importer's centring.
CENTRING = ("use_center", "put_to_center")


def load():
    spec = importlib.util.spec_from_file_location("pdb_to_printable_stl",
                                                  VENDORED)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def uncentred(build):
    """``build_import_kwargs`` with every centring key it set turned
    off."""
    def build_import_kwargs(cfg):
        kwargs = build(cfg)
        for name in CENTRING:
            if name in kwargs:
                kwargs[name] = False
        return kwargs
    return build_import_kwargs


def main():
    script = load()
    script.build_import_kwargs = uncentred(script.build_import_kwargs)
    return script.main()


if __name__ == "__main__":
    code = main()
    if bpy.app.background:
        sys.exit(code)
