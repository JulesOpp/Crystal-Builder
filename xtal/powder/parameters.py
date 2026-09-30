"""The numbers a refinement starts from, and which of them it moves.

Every run in the workbench used to start from RietX's preset: a
Pawley fit's peak shape was thrown away before the Rietveld step
began, and With energy fitted the scale, background and profile again
from nothing, where nobody could see it.  A :class:`ParameterSet` is
what is kept between runs instead -- every number with its value,
whether it is refined, and the esd the last fit gave it -- and it is
one set for every step, so switching step keeps it.

Named for a person, mapped to RietX's paths in one place.  **This
module never imports RietX**: ``bridge`` hands a set's values to a
refinement and takes them back.  The cell is not here -- each step
keeps its own (Pawley a trial cell, Rietveld the structure's) -- and
an atom's Biso and occupancy are the structure's, carried here as
``owner="structure"`` so that the table can show them and send an edit
to the Document rather than keep a second copy that drifts.

The text form, which Copy and Paste use, is one row a line::

    zero_error 0.0011987 ± 0.00030 Refine
    sample_displacement 0 NoRefine
    Ti1_xyz Refine
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

import numpy as np

from xtal.core import elements as el
from xtal.powder.data import PowderError

#: Biso from Uiso.
B_PER_U = 8.0 * math.pi ** 2

#: Biso for a site that gives none -- a typical room-temperature value.
DEFAULT_BISO = 0.5

#: The fraction of the counts below which the background starts.  Not
#: the median, which a pattern of crowded peaks lifts off the floor:
#: rutile's 100-count background is 100 at the median and 91 here, and
#: a MOF's crowded low angles only push the median further up.
BACKGROUND_PERCENTILE = 20.0

SCALE = "Scale"
BACKGROUND = "Background"
POSITIONS = "Line positions"
PROFILE = "Peak shape"
SAMPLE = "Sample broadening"
TEXTURE = "Preferred orientation"
ATOMS = "Atoms"

#: The groups in the order they are shown and freed: McCusker's.
GROUPS = (SCALE, BACKGROUND, POSITIONS, PROFILE, SAMPLE, TEXTURE, ATOMS)

#: ``(name, label, group, path, refined by default)`` of every row that
#: is not a background coefficient or an atom's.
_FIXED = (
    ("scale", "Scale", SCALE, "phases.0.scale", True),
    ("zero_error", "Zero error", POSITIONS, "instrument.zero_shift",
     False),
    ("sample_displacement", "Specimen displacement", POSITIONS,
     "instrument.geometry.sample_displacement", True),
    ("U", "U", PROFILE, "instrument.profile.u", True),
    ("V", "V", PROFILE, "instrument.profile.v", True),
    ("W", "W", PROFILE, "instrument.profile.w", True),
    ("X", "X", PROFILE, "instrument.profile.x", True),
    ("Y", "Y", PROFILE, "instrument.profile.y", True),
    ("cs_l", "Size, Lorentzian", SAMPLE, "phases.0.lor_size", False),
    ("cs_g", "Size, Gaussian", SAMPLE, "phases.0.gauss_size", False),
    ("strain_l", "Strain, Lorentzian", SAMPLE, "phases.0.lor_strain",
     False),
    ("strain_g", "Strain, Gaussian", SAMPLE, "phases.0.gauss_strain",
     False),
    ("po_r", "March-Dollase r", TEXTURE,
     "phases.0.preferred_orientation.r", False),
)

#: What a row with no preset value starts at: r = 1 is no texture.
_START = {"phases.0.preferred_orientation.r": 1.0}

#: Which of the old "Refine ..." boxes each row answers to, by path: the
#: words the bridge's plan and ``xtal run``'s boxes are in.
_BOXES = {
    "phases.0.scale": "scale",
    "instrument.zero_shift": "zero",
    "instrument.geometry.sample_displacement": "displacement",
    "phases.0.lor_size": "size", "phases.0.gauss_size": "size",
    "phases.0.lor_strain": "strain", "phases.0.gauss_strain": "strain",
    "phases.0.preferred_orientation.r": "preferred_orientation",
}

_BACKGROUND = re.compile(r"bkg_c(\d+)$")
_FLAGS = {"refine": True, "norefine": False}


@dataclass
class Parameter:
    """One row: a number, whether it is refined, and its esd.

    ``value`` is ``None`` for a row that is only a flag -- an atom's
    position, which is three numbers the structure holds and the
    symmetry decides how many of are free.  ``held`` is why RietX will
    not move it (a locked angle, a tied coordinate), ``""`` when it
    will; a held row is shown and never set.
    """

    name: str
    label: str
    group: str
    path: str
    value: float | None
    refine: bool
    esd: float | None = None
    owner: str = "refinement"
    held: str = ""


class ParameterSet:
    """Every row, in the order they are shown."""

    def __init__(self, rows=()):
        self._rows: dict[str, Parameter] = {}
        for row in rows:
            self._rows[row.name] = row

    def __iter__(self):
        return iter(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __str__(self) -> str:
        """One line, as a run log's header lists what a run was handed:
        the whole set is in ``parameters-start.txt`` beside it."""
        flagged = len(self.freed_paths())
        return (f"{len(self)} parameters, {flagged} refined "
                f"(parameters-start.txt)")

    def __contains__(self, name) -> bool:
        return name in self._rows

    def __getitem__(self, name: str) -> Parameter:
        return self._rows[name]

    def copy(self) -> ParameterSet:
        return ParameterSet(replace(row) for row in self)

    def names(self) -> list[str]:
        return list(self._rows)

    def in_group(self, group: str) -> list[Parameter]:
        return [row for row in self if row.group == group]

    # ------------------------------------------------------ editing

    def set_value(self, name: str, value: float) -> None:
        """A number typed in: its esd belongs to the old value, so it
        goes."""
        row = self._rows[name]
        if row.value is None:
            raise PowderError(f"{name} is a flag and has no value")
        row.value, row.esd = float(value), None

    def set_refine(self, name: str, refine: bool) -> None:
        self._rows[name].refine = bool(refine)

    def set_group_refine(self, group: str, refine: bool) -> None:
        """Every row of ``group`` on or off -- what one of the old
        "Refine ..." boxes did."""
        for row in self.in_group(group):
            row.refine = bool(refine)

    # --------------------------------------------------- background

    @property
    def background_terms(self) -> int:
        return len(self.in_group(BACKGROUND))

    def set_background_terms(self, terms: int) -> None:
        """Grow or shrink the Chebyshev series.  The coefficients it
        has are kept: raising the order is how a person follows a
        background that bends, and it must not throw away the level
        and slope the last fit found."""
        terms = max(int(terms), 1)
        have = self.in_group(BACKGROUND)
        refine = have[0].refine if have else True
        kept = {row.name: row for row in have[:terms]}
        new = [kept.get(f"bkg_c{n}") or _background_row(n, 0.0, refine)
               for n in range(terms)]
        self._put_group(BACKGROUND, new)

    def _put_group(self, group: str, rows) -> None:
        """``rows`` in the place ``group`` has, the rest kept in order."""
        out: dict[str, Parameter] = {}
        placed = False
        rank = GROUPS.index(group)
        for row in self:
            if row.group == group:
                continue
            if not placed and GROUPS.index(row.group) > rank:
                out.update((r.name, r) for r in rows)
                placed = True
            out[row.name] = row
        if not placed:
            out.update((r.name, r) for r in rows)
        self._rows = out

    # ------------------------------------------------ to and from a fit

    def values_by_path(self) -> dict[str, float]:
        """``{path: value}`` of every number a refinement is handed:
        not the held rows, which RietX would refuse, and not the flags,
        which have no number."""
        return {row.path: row.value for row in self
                if row.value is not None and not row.held}

    def freed_paths(self) -> list[str]:
        """RietX's paths, or globs, of every row to refine."""
        return [row.path for row in self if row.refine and not row.held]

    def flag_boxes(self, free) -> None:
        """Refine what the old boxes named and nothing else -- how
        ``xtal run`` with no parameter file still means what it did.
        ``free`` is in the bridge's words (``"background"``,
        ``"positions"``); the scale is always refined, as it always
        was."""
        free = set(free) | {"scale"}
        for row in self:
            row.refine = box_of(row.path) in free

    def take(self, values: dict[str, float],
             esds: dict[str, float], groups=None) -> None:
        """A finished fit's numbers: every value it reports, and an esd
        for what it refined.  A row it did not refine loses its esd --
        an esd from an earlier run describes a value that has not
        changed, but also a model that has.  With ``groups``, only
        those groups' rows are touched: a Pawley fit has a scale, and
        it is not the one a Rietveld run should start from."""
        for row in self:
            if groups is not None and row.group not in groups:
                continue
            if row.value is not None and row.path in values:
                row.value = float(values[row.path])
            esd = esds.get(row.path)
            row.esd = float(esd) if esd else None

    def hold(self, reasons: dict[str, str]) -> None:
        """Mark what RietX will not move, ``{path: why}``; a row not
        named is free again."""
        for row in self:
            row.held = reasons.get(row.path, "")

    def reset(self, defaults: ParameterSet) -> None:
        """Every number the refinement owns back to ``defaults``'s --
        for when the background or the size broadening has run away.
        What is refined is the person's choice and is kept, and the
        structure's numbers are the structure's: Ctrl+Z is how those
        go back.  The background keeps as many terms as it has, and a
        coefficient the defaults do not have goes to zero -- it is the
        high ones that run away."""
        for row in self:
            if row.owner != "refinement":
                continue
            if row.name in defaults:
                row.value = defaults[row.name].value
            elif row.group == BACKGROUND:
                row.value = 0.0
            row.esd = None

    # ---------------------------------------------------- text form

    def to_text(self) -> str:
        """One row a line, as Copy puts it on the clipboard.  A held
        row is written as a comment: it says what the number is, and
        reading it back sets nothing."""
        lines = []
        group = None
        for row in self:
            if row.group != group:
                group = row.group
                lines.append(f"# {group}")
            words = [row.name]
            if row.value is not None:
                words.append(format_value(row.value, row.esd))
            words.append("Refine" if row.refine else "NoRefine")
            line = " ".join(words)
            lines.append(f"# {line}  (held: {row.held})" if row.held
                         else line)
        return "\n".join(lines) + "\n"

    def paste(self, text: str) -> int:
        """Read rows in the text form into this set; how many were read.

        All or nothing: every line is read before any row is changed,
        so a typo on the last line leaves the set as it was rather than
        half pasted.  A row the text does not name keeps its value, so
        a few lines can be pasted as well as a whole set.  A background
        coefficient beyond the series grows it.
        """
        changes = []
        terms = self.background_terms
        for number, line in enumerate(text.splitlines(), start=1):
            words = line.split("#", 1)[0].split()
            if not words:
                continue
            name, flag = words[0], words[-1].lower()
            where = f"line {number}"
            if flag not in _FLAGS or len(words) < 2:
                raise PowderError(f"{where}: {line.strip()!r} does not "
                                  f"end in Refine or NoRefine")
            middle = words[1:-1]
            background = _BACKGROUND.match(name)
            if name not in self and background is None:
                raise PowderError(f"{where}: there is no parameter "
                                  f"called {name!r}")
            if background is not None:
                terms = max(terms, int(background.group(1)) + 1)
            flag_only = name in self and self[name].value is None
            value, esd = _read_numbers(middle, where)
            if flag_only and value is not None:
                raise PowderError(f"{where}: {name} is a flag and takes "
                                  f"no value")
            changes.append((name, value, esd, _FLAGS[flag]))
        if terms > self.background_terms:
            self.set_background_terms(terms)
        for name, value, esd, refine in changes:
            row = self._rows[name]
            if value is not None:
                row.value, row.esd = value, esd
            row.refine = refine
        return len(changes)


# ======================================================================
#  BUILDING A SET
# ======================================================================

def box_of(path: str) -> str:
    """The box a row's path answers to, ``""`` for none."""
    if path.endswith(".dof.*"):
        return "positions"
    if path.endswith(".biso"):
        return "biso"
    if path.endswith(".occ"):
        return "occupancy"
    if path.startswith("instrument.background."):
        return "background"
    if path.startswith("instrument.profile."):
        return "profile"
    return _BOXES.get(path, "")


def site_labels(structure) -> list[tuple[int, str]]:
    """``[(site_index, label), ...]`` of the atoms that scatter, in the
    order RietX is handed them.

    Dummy atoms are markers and are left out.  Two sites called O1
    would be one parameter in RietX's paths, so the second is made
    unique -- here, once, for the bridge and the table alike.
    """
    out = []
    taken: set[str] = set()
    for index, site in enumerate(structure.sites):
        if el.is_dummy(site.element):
            continue
        label = site.label or f"{site.element}{index + 1}"
        if label in taken:
            label = f"{label}_{index + 1}"
        taken.add(label)
        out.append((index, label))
    return out


def site_biso(site) -> float:
    """The Biso a site is refined from."""
    u = site.u_equivalent
    return DEFAULT_BISO if not u else float(u) * B_PER_U


def atom_rows(structure) -> list[Parameter]:
    """A position flag, a Biso and an occupancy for every atom that
    scatters.  The values are the structure's, and so is any edit to
    them."""
    rows = []
    for k, (index, label) in enumerate(site_labels(structure)):
        site = structure.sites[index]
        name = re.sub(r"\s+", "_", label)
        base = f"phases.0.atoms.{k}"
        rows += [
            Parameter(f"{name}_xyz", f"{label} position", ATOMS,
                      f"{base}.dof.*", None, True, owner="structure"),
            Parameter(f"{name}_biso", f"{label} Biso", ATOMS,
                      f"{base}.biso", site_biso(site), True,
                      owner="structure"),
            Parameter(f"{name}_occ", f"{label} occupancy", ATOMS,
                      f"{base}.occ", float(site.occupancy), False,
                      owner="structure"),
        ]
    return rows


def defaults(preset: dict[str, float], *, structure=None, data=None,
             synchrotron: bool = False) -> ParameterSet:
    """The set a first run starts from, and what Reset goes back to.

    ``preset`` is RietX's instrument for this radiation as
    ``{path: value}`` (``bridge.preset_parameters``); its background
    coefficients say how many terms there are.  With ``data``, the
    background starts under the counts rather than at zero.  A
    capillary has no specimen displacement to refine.
    """
    rows = []
    for name, label, group, path, refine in _FIXED:
        value = preset.get(path, _START.get(path, 0.0))
        if name == "sample_displacement" and synchrotron:
            refine = False
        rows.append(Parameter(name, label, group, path, float(value),
                              refine))
    terms = sum(1 for path in preset
                if path.startswith("instrument.background.c")) or 1
    level = 0.0
    if data is not None and len(data):
        level = float(np.percentile(data.intensity,
                                    BACKGROUND_PERCENTILE))
    background = [_background_row(n, level if n == 0 else 0.0, True)
                  for n in range(terms)]
    rows = rows[:1] + background + rows[1:]
    if structure is not None:
        rows += atom_rows(structure)
    return ParameterSet(rows)


def with_structure(parameters: ParameterSet, structure) -> ParameterSet:
    """``parameters`` with its atom rows made from ``structure`` again.

    The values are the structure's -- it is where they live -- and
    what is refined, and what the last fit found held, are kept for
    every atom still called what it was, so an edit to the structure
    does not undo a person's choices.  The esd goes with a value that
    changed, since it described the old one.
    """
    out = parameters.copy()
    old = {row.name: row for row in out.in_group(ATOMS)}
    rows = atom_rows(structure)
    for row in rows:
        was = old.get(row.name)
        if was is None:
            continue
        row.refine, row.held = was.refine, was.held
        # a Biso goes to the site as U and comes back, a rounding apart
        if was.value is None or (row.value is not None and math.isclose(
                was.value, row.value, rel_tol=1e-9)):
            row.esd = was.esd
    out._put_group(ATOMS, rows)
    return out


def site_fields(structure) -> dict[str, tuple[int, str]]:
    """``{row name: (site index, "biso" | "occupancy")}`` of the rows
    whose number is a site's -- where an edit made in the table goes."""
    out = {}
    for index, label in site_labels(structure):
        name = re.sub(r"\s+", "_", label)
        out[f"{name}_biso"] = (index, "biso")
        out[f"{name}_occ"] = (index, "occupancy")
    return out


# ======================================================================
#  NUMBERS
# ======================================================================

def format_value(value: float, esd: float | None = None) -> str:
    """``0.0011987 ± 0.00030``: the esd to two figures and the value to
    two places beyond it, or the value alone to ten figures.

    Two places beyond the esd rather than the esd's own last place, so
    that Copy and Paste move a number by a hundredth of its esd at
    most -- a zero-cycle run on pasted numbers gives the R values the
    copied ones did.
    """
    if esd is None or not esd > 1e-12 or not math.isfinite(esd):
        return f"{value:.10g}"
    places = max(0, 1 - math.floor(math.log10(esd)))
    return f"{value:.{places + 2}f} ± {esd:.{places}f}"


def _read_numbers(words, where: str):
    """``(value, esd)`` from what sits between a name and its flag."""
    if not words:
        return None, None
    if len(words) == 3 and words[1] in ("±", "+/-", "+-"):
        return _number(words[0], where), _number(words[2], where)
    if len(words) == 1:
        return _number(words[0], where), None
    raise PowderError(f"{where}: expected a value, or a value ± esd, "
                      f"and read {' '.join(words)!r}")


def _number(word: str, where: str) -> float:
    try:
        value = float(word)
    except ValueError:
        raise PowderError(f"{where}: {word!r} is not a number") from None
    if not math.isfinite(value):
        raise PowderError(f"{where}: {word!r} is not a number")
    return value


def _background_row(n: int, value: float, refine: bool) -> Parameter:
    return Parameter(f"bkg_c{n}", f"c{n}", BACKGROUND,
                     f"instrument.background.c{n}", float(value), refine)
