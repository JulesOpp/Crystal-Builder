# Measure the porosity and the powder pattern of a structure
Measure the porosity of $path and its powder pattern.

1. Call `guide` with the topic `porosity` and read it; `capabilities`
   says which porosity entries this install can run.
2. `open` $path and `inspect`. Prepare a structure from a database or
   a paper first (the `prepare` guide): solvent left in the pores is
   counted as framework.
3. `run` the pore volume, surface area and pore size entries the guide
   names, then the PXRD pattern.
4. Quote each number with its probe, radii and source, and the pattern
   with its radiation. A window flagged borderline is unresolved: say
   so, and never round it to open or closed.
5. Give me every diagnostic by its code and where the run folders are.
