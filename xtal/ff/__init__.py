"""
xtal.ff
=======
Energy, forces and geometry optimisation.

Importing this package registers every engine that ships in-tree --
which today means UFF and nothing else, and is meant to stay a
one-line change when it means more.

    from xtal.ff import ENGINES, optimize
    calculator = ENGINES.build("uff", structure)
    result = calculator.compute(cell.cart, structure.lattice.matrix)
    print(result.energy, result.max_force)

Everything here is headless, like the rest of ``xtal``: the panel, the
worker thread and the live plot are in ``xtalapp`` and are a thin shell
over this.
"""

from xtal.ff.api import Calculator, CalculatorError, Result
from xtal.ff.dftb.calculator import DFTBCalculator, DFTBOptions
from xtal.ff.mace.calculator import MACECalculator, MACEOptions
from xtal.ff.orb.calculator import ORBCalculator, ORBOptions
from xtal.ff.registry import ENGINES, Engine, EngineRegistry
from xtal.ff.uff.calculator import UFFCalculator, UFFOptions
from xtal.ff.uff.typer import Typing, TypingError
from xtal.ff.xtb.calculator import XTBCalculator, XTBOptions

__all__ = ["Calculator", "CalculatorError", "Result", "ENGINES",
           "Engine", "EngineRegistry", "UFFCalculator", "UFFOptions",
           "DFTBCalculator", "DFTBOptions", "XTBCalculator", "XTBOptions",
           "MACECalculator", "MACEOptions", "ORBCalculator",
           "ORBOptions", "Typing", "TypingError"]
