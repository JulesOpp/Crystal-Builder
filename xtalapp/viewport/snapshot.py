"""
xtalapp.viewport.snapshot
=========================
Draw a project file to a PNG, offscreen, and exit -- the half of
:func:`xtal.agent.render.render` that needs VTK.

Run as ``python -m xtalapp.viewport.snapshot PROJECT OUT.png ARGS``,
always in a process of its own: on a machine with no OpenGL, VTK
reaches an access violation in C++ rather than raising, and the
process that asked for the picture must survive that.  No Qt: the
scene model and the VTK scene are the viewport's own, without the
widget around them.
"""

from __future__ import annotations

import ast
import sys

import numpy as np


def _direction(lattice, view) -> np.ndarray:
    matrix = np.asarray(lattice.matrix, dtype=float)
    if isinstance(view, str):
        if view == "diagonal":
            return np.array([1.0, 1.0, 0.6])
        # Looking *down* an axis means standing on its far end.
        return -matrix["abc".index(view)]
    return -np.asarray(lattice.to_cart(np.asarray(view, float)))


def draw(project, out, args) -> None:
    """The half that runs in the subprocess, and may die there."""
    from vtkmodules.vtkIOImage import vtkPNGWriter
    from vtkmodules.vtkRenderingCore import (
        vtkRenderWindow,
        vtkWindowToImageFilter,
    )

    from xtal.core.selection import Selection
    from xtal.io.project import read_project
    from xtalapp.viewport.builder import build_scene
    from xtalapp.viewport.view_settings import ViewSettings
    from xtalapp.viewport.vtk_scene import VtkScene

    structure, _view, _session = read_project(project)
    settings = ViewSettings(style=args["style"],
                            show_cell=args["show_cell"])
    selection = Selection(atoms=set(args["highlight"]))
    model = build_scene(structure, settings, selection=selection)
    scene = VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(*args["size"])
    window.AddRenderer(scene.renderer)
    # Orthographic: under perspective the near face of a cell is
    # bigger than the far one, and a straight channel looks like a
    # funnel -- a thing an agent would then try to explain.
    scene.set_projection("orthographic")
    scene.reset_camera()
    scene.look_along(_direction(structure.lattice, args["view"]))
    scene.renderer.ResetCamera()
    window.Render()
    grabber = vtkWindowToImageFilter()
    grabber.SetInput(window)
    grabber.Update()
    writer = vtkPNGWriter()
    writer.SetFileName(str(out))
    writer.SetInputConnection(grabber.GetOutputPort())
    writer.Write()
    window.Finalize()


if __name__ == "__main__":
    draw(sys.argv[1], sys.argv[2], ast.literal_eval(sys.argv[3]))
