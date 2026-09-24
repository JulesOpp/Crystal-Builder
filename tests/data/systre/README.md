# What Systre said about the nets this application writes

Written 2026-09-24.  `File > Export Net for Systre` was only ever
checked by reading its own file back, which is not an independent
check.  These two nets were exported by `xtal.io.cgd.entry_of` and
`write_cgd`, and run through Systre 19.6.0
(`github.com/odf/gavrog`, release `Systre-19.6.0.jar`, SHA-256
`0d272e98a1a21669bc67a809b95c014ba2a2fb39a6fd2147039201216ab0d48d`)
on Java 8:

    java -cp Systre-19.6.0.jar org.gavrog.apps.systre.SystreCmdline mof5_net.cgd

| file | drawn as | Systre |
|---|---|---|
| `mof5_net.cgd` | `resources/samples/MOF-5.cif`, each Zn4O cluster's central oxygen a vertex, joined to the six 12.93 A away | **pcu**, ideal group Pm-3m |
| `rutile_net.cgd` | the `rutile` fixture, every perceived Ti-O bond an edge | **rtl**, ideal group P4_2/mnm |

`*.systre.txt` is Systre's whole output.  `tests/test_cgd.py` makes the
two nets again and requires these files byte for byte, so a change to
the writer that changes either one fails there -- and the answer is to
run Systre on the new file, not to copy it over the old one.
