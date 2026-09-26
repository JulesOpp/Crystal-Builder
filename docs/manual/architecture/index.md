# Architecture of Crystal Builder

How the program is put together, for a reader who wants to extend it
or to understand why it behaves as it does: a headless core with a
window over it, one Document that every edit goes through, the
registries that menus, modules and engines are built from, and the
seams a plug-in or an external program fits into.  After this chapter
you can find the file a feature lives in, add a command or a module
where the existing ones are, and run the checks that keep the two
halves apart.

This chapter is about software, not chemistry.  Everything in it is
taken from the repository as it is -- its layout, its docstrings, its
tests and its continuous-integration configuration -- and from runs
made while writing it; where a statement is about a version, it is
the version named on the title page.  The methods themselves are in
the chapters before this one, and the full list of commands, settings
and panels is the {ref}`generated reference <reference-appendix>`.

:::{note}
None of the names on these pages is a stable interface.  They are
the ones the code uses today, given so that a contributor can find
them; the {doc}`scripting page </workflows/scripting>` says the same
of the core's Python entry points, and the same advice applies: pin
the version you work against.
:::

```{toctree}
:maxdepth: 1

layers
document
registries
plugins
testing
```
