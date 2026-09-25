# Crystal Builder Manual

```{only} html
Release {{ release }}
```

```{raw} latex
\setcounter{secnumdepth}{-1}
```

% No caption: LaTeX titles the contents page with the first
% toctree's caption, and this one would be "Front matter".
```{toctree}
:maxdepth: 1

front/foreword
front/highlights
front/cite
front/using-this-manual
```

```{raw} latex
\setcounter{secnumdepth}{2}
\setcounter{chapter}{0}
```

```{toctree}
:maxdepth: 2
:numbered: 2
:caption: Manual

quickstart/index
essentials/index
energy/index
structure/index
porosity/index
frameworks/index
workflows/index
utilities/index
architecture/index
```

```{raw} latex
\appendix
```

```{toctree}
:maxdepth: 1
:caption: Appendices

back/reference
back/changelog
back/glossary
back/bibliography
```
