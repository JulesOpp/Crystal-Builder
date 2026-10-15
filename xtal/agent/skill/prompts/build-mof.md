# Build a metal-organic framework on a net
Build a framework on the net $topology with the node $node and the
edge $edge.

1. Call `guide` with the topic `mof` and read it.
2. `build` with the `mof.build` action, passing them as `topology`,
   `nodes` and `edges`, into the workspace.
3. Read the build's own table: an RMSD near 0, a closest contact above
   about 1.5 A, and the net that came out the same as $topology. A
   `BUILD_OVERLAP` warning means atoms of two blocks overlap: report
   it, and run no calculation on the result.
4. `inspect` the result: the formula, every metal's coordination, the
   fragments.
5. `save`, and give me the path, the build's table and every
   diagnostic by its code.
