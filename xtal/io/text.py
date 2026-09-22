"""Reading a text file the way the files people have are written.

Every reader names its encoding, and ``utf-8`` is the right one to
write; it is not quite the right one to read.  Notepad, Excel,
PowerShell's ``Out-File`` and a good deal of Java crystallography
tooling put a byte-order mark at the front of a UTF-8 file, and under
``utf-8`` those three invisible bytes become the first character of
line one -- so a perfect CIF was "expected block header", a perfect
XYZ "must be an atom count", each reader blaming the wrong line.
``utf-8-sig`` is ``utf-8`` that drops the mark when there is one.
"""

from __future__ import annotations

from pathlib import Path

BOM = b"\xef\xbb\xbf"


def read_text(path) -> str:
    """The file's text, without a byte-order mark.

    A byte that is not UTF-8 -- a pre-2010 CIF written in Latin-1 --
    is otherwise a ``UnicodeDecodeError`` quoting an offset and not
    the file, which is no help to somebody with a folder of them.
    """
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"{path.name} is not UTF-8 text (byte {error.start} is "
            f"0x{error.object[error.start]:02x}); re-save it as UTF-8"
        ) from error


def has_bom(path) -> bool:
    with open(path, "rb") as handle:
        return handle.read(len(BOM)) == BOM
