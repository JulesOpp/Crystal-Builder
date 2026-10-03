"""
xtal.polymer.sequence
=====================
Which monomer comes next, and which hand it is.

Two independent choices per unit, made before any geometry:

* **Composition** -- a homopolymer, or a copolymer of monomers A, B,
  ... *alternating*, *random* by fraction, or in *blocks* of given
  lengths repeated down the chain.
* **Tacticity** -- whether each unit is the same hand as the one
  before it.  A stereocentre's configuration is the embedding's or its
  mirror (:meth:`xtal.polymer.monomer.Monomer.mirrored`), so a *meso*
  dyad is two units of one hand and a *racemo* dyad two of opposite
  hands: *isotactic* is all meso, *syndiotactic* all racemo, and
  *atactic* is meso with probability ``p_meso`` (0.5 is Bernoullian
  and is what a free-radical polymerisation gives, near enough).

A monomer with no stereocentre comes back from its mirror as the same
molecule, so asking for tacticity of polyethylene is harmless and
changes nothing.

Everything random is drawn from the ``numpy`` generator passed in, so a
seed builds the same chain twice.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

COMPOSITIONS = ("homopolymer", "alternating", "random", "block")
TACTICITIES = ("isotactic", "syndiotactic", "atactic")


class SequenceError(ValueError):
    """A recipe that names no chain, said in a sentence."""


@dataclass(frozen=True)
class Sequence:
    """How a chain's units are chosen.

    ``fractions`` is for *random* (one per monomer, normalised here);
    ``blocks`` is for *block*, the length of each monomer's run, in
    monomer order, repeated until the chain is long enough.
    """

    composition: str = "homopolymer"
    tacticity: str = "atactic"
    p_meso: float = 0.5
    fractions: tuple[float, ...] = ()
    blocks: tuple[int, ...] = ()

    def check(self, n_monomers: int) -> None:
        """Refuse what cannot be drawn, before anything is built."""
        if self.composition not in COMPOSITIONS:
            raise SequenceError(
                f"no composition called {self.composition!r}; the "
                f"choices are {', '.join(COMPOSITIONS)}")
        if self.tacticity not in TACTICITIES:
            raise SequenceError(
                f"no tacticity called {self.tacticity!r}; the choices "
                f"are {', '.join(TACTICITIES)}")
        if not 0.0 <= self.p_meso <= 1.0:
            raise SequenceError(f"p(meso) is a probability, and "
                                f"{self.p_meso} is not one")
        if n_monomers < 1:
            raise SequenceError("a chain needs a monomer")
        if self.composition == "homopolymer" and n_monomers != 1:
            raise SequenceError(
                f"a homopolymer is one monomer, and {n_monomers} were "
                f"given -- a copolymer is alternating, random or block")
        if self.composition != "homopolymer" and n_monomers < 2:
            raise SequenceError(f"a {self.composition} copolymer needs "
                                f"two monomers or more")
        if self.composition == "random":
            if len(self.fractions) != n_monomers:
                raise SequenceError(
                    f"a random copolymer needs a fraction for each of "
                    f"its {n_monomers} monomers")
            if any(f < 0 for f in self.fractions) or not sum(
                    self.fractions) > 0:
                raise SequenceError("the fractions must be positive")
        if self.composition == "block":
            if len(self.blocks) != n_monomers or any(
                    b < 1 for b in self.blocks):
                raise SequenceError(
                    f"a block copolymer needs a block length of one or "
                    f"more for each of its {n_monomers} monomers")


def draw(sequence: Sequence, n_monomers: int, length: int,
         rng: np.random.Generator) -> list[tuple[int, bool]]:
    """``(which monomer, mirrored)`` for each of ``length`` units."""
    sequence.check(n_monomers)
    if sequence.composition == "homopolymer":
        which = [0] * length
    elif sequence.composition == "alternating":
        which = [k % n_monomers for k in range(length)]
    elif sequence.composition == "random":
        p = np.asarray(sequence.fractions, float)
        which = [int(i) for i in rng.choice(n_monomers, size=length,
                                            p=p / p.sum())]
    else:
        pattern = [i for i, n in enumerate(sequence.blocks)
                   for _ in range(n)]
        which = [pattern[k % len(pattern)] for k in range(length)]

    hands: list[bool] = []
    for k in range(length):
        if k == 0:
            hands.append(False)
        elif sequence.tacticity == "isotactic":
            hands.append(hands[-1])
        elif sequence.tacticity == "syndiotactic":
            hands.append(not hands[-1])
        else:
            meso = rng.random() < sequence.p_meso
            hands.append(hands[-1] if meso else not hands[-1])
    return list(zip(which, hands, strict=True))


def units(monomers, drawn) -> list:
    """The monomers a drawn sequence names, each the hand it says --
    mirrored once per monomer, not once per unit."""
    mirrored = [m.mirrored() for m in monomers]
    return [mirrored[i] if hand else monomers[i] for i, hand in drawn]
