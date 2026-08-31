"""
xtal.plugins
============
Registration from outside the tree.

Everything the application can do that is not crystallography itself
is a registry entry: file formats, draw styles, force-field engines
and now modules.  In-tree entries register themselves when their
package is imported.  This is the other half -- a package installed
beside this one, declaring::

    [project.entry-points."crystal_builder.plugins"]
    zeopp = "zeopp_plugin:register"

whose ``register()`` is called once, at start-up, and may register into
any of the four registries.  That is what makes the claim in
:doc:`docs/PLAN` § 14 -- *no existing file changes* -- literally true
rather than nearly true.

Two rules, both learned from applications that got this wrong.

**A plugin that raises must not take the application with it.**  A
broken or half-installed plugin is a warning in the log and an entry
in :attr:`failures`, not a window that will not open.

**Loading happens once and is idempotent.**  It is called from the
GUI's start-up and from the CLI, and both may run in the same process
during tests; a second call is free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GROUP = "crystal_builder.plugins"


@dataclass
class LoadReport:
    """What happened the one time plugins were loaded."""

    loaded: list = field(default_factory=list)      # names
    failures: list = field(default_factory=list)    # (name, message)

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if not self.loaded and not self.failures:
            return "no plugins installed"
        parts = []
        if self.loaded:
            parts.append(f"loaded {', '.join(sorted(self.loaded))}")
        for name, message in self.failures:
            parts.append(f"{name} failed to load: {message}")
        return "; ".join(parts)


_report: LoadReport | None = None


def load(force: bool = False) -> LoadReport:
    """Call every registered plugin's entry point, once."""
    global _report
    if _report is not None and not force:
        return _report
    from importlib.metadata import entry_points

    report = LoadReport()
    try:
        found = entry_points(group=GROUP)
    except Exception as exc:                        # noqa: BLE001
        report.failures.append(("entry points", str(exc)))
        found = ()
    for entry in found:
        try:
            register = entry.load()
            register()
            report.loaded.append(entry.name)
        except Exception as exc:                    # noqa: BLE001
            # Deliberately broad: a plugin can fail in any way an
            # import can, and none of them is a reason for the
            # application not to open.
            report.failures.append((entry.name, str(exc)))
    _report = report
    return report


def report() -> LoadReport | None:
    """What the last load found, or ``None`` if it has not run."""
    return _report
