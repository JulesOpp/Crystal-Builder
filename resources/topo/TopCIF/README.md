# TopCIF

The RCSR topology CIFs, as downloaded.  Nothing in this project reads
them: the net index is built from `../RCSRnets-2019-06-01.cgd` by
`python -m xtal.analysis.rcsr build`, and the built index ships as
package data.  They are here as the reference the `.cgd` came with.

## `nul-net.cif`

That file is the RCSR net **nul**, and it is renamed rather than named
after its net.

`nul` is a reserved device name on Windows, as are `con`, `prn`, `aux`,
`com1`–`com9` and `lpt1`–`lpt9`, with or without an extension.  Git
cannot create such a path, so `git checkout` fails outright:

    error: invalid path 'resources/topo/TopCIF/nul.cif'
    fatal: unable to checkout working tree

That is not a warning about one file.  **The whole checkout fails**, so
the repository could not be cloned on Windows at all, and the Windows
CI job had been failing at the checkout step — before installing
anything, before running a test — for as long as the file had been
here.

`tests/test_packaging.py` has a test that fails if another reserved
name is ever added.
