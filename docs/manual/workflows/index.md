# Workflows and the Command Line

Everything the window runs, the `xtal` command runs without it -- into
the same workspace, leaving the same files.  This chapter is where a
scripting user starts: the command and each of its subcommands, what
a workspace and a run folder look like on disk, what a run leaves
behind and how to read it from a script, the core as a Python
library, and what to record so that a result can be repeated.

The science is in the chapters before this one.  Where a command here
runs a method -- a force field, a relaxation, a scan, a builder -- the
page links to the chapter that explains it rather than repeating it:
{doc}`energy models </energy/index>`, {doc}`structure and
optimisation </structure/index>`, {doc}`porosity and properties
</porosity/index>` and {doc}`frameworks and nets </frameworks/index>`.

```{toctree}
:maxdepth: 1

cli
workspaces
reports
scripting
reproducing
```
