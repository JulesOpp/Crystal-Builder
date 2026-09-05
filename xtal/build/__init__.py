"""
xtal.build
==========
A molecule that does not exist yet, from a SMILES string.

There is no way to make a benzoate in this application except by
placing eleven atoms by hand, and this is the answer to that.  It is
headless, imports no Qt, and -- the part that shapes the package --
imports no RDKit either until something actually builds a molecule.

**RDKit is required for the feature and absent for everybody else.**
It is a large wheel with a compiled core, and the four packages the
core installs are what make ``pip install crystal-builder`` usable on
a cluster node.  So it is the ``build`` extra, :func:`installed` is
``find_spec`` and never an import, and without it the menu entry greys
out saying so -- the pattern :mod:`xtal.modules.mof` established for
PORMAKE, and for the same reason: a check that costs an import is a
check nothing can afford to run on every menu rebuild.

**A second thing is built here and shares none of that.**
:mod:`xtal.build.topology` draws a named RCSR net as a structure, and
it needs numpy and the ``.cgd`` reader and nothing else -- no extra,
no optional import, nothing to grey out.  It is in this package
because this is where a structure that did not exist before is made,
and it is not re-exported below because importing it pulls in the
catalogue: ``from xtal.build import topology`` is the way in.

Connection points are ``*`` in SMILES and ``X`` -- see
:data:`~xtal.core.elements.DUMMY_ELEMENTS` -- in the structure that
comes out, which is what :mod:`xtal.mof.catalog` already calls a
connection point.  Choosing the dummy that already exists means
perception, the force field and every module run hold them back at the
door already; choosing a real element -- radon was the suggestion --
would have meant teaching all three about a second symbol, and would
have put a radon atom in every CIF this ever wrote.
"""

from __future__ import annotations

from xtal.build.chem import MISSING, BuildError, installed
from xtal.build.molecule import Molecule, from_smiles

__all__ = ["MISSING", "BuildError", "installed", "Molecule",
           "from_smiles"]
