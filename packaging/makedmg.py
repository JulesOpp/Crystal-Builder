"""
Wrap the built ``.app`` in a DMG.

    python packaging/makedmg.py "dist/Crystal Builder.app" dist/

**``hdiutil`` and not ``create-dmg``**, and that is a decision rather
than a simplification.  ``create-dmg`` positions the icons in the
mounted window by driving Finder over Apple events, and anything
without macOS Automation permission is refused:

    execution error: Not authorized to send Apple events to Finder.
    (-1743)

A developer can grant that in System Settings; a CI runner cannot be
asked, and a build that works on one machine and not the next is not
a build step.  What the AppleScript buys is a background image and
icon positions, which PACKAGING.md § 5 already puts outside phase 8.
What it does not affect is anything functional: the volume name, the
application, and the ``/Applications`` symlink to drag it to are all
plain filesystem, and they are what this writes.

``UDZO`` is zlib-compressed and read-only, which is what a download
should be.  It roughly halves the bundle.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VOLUME = "Crystal Builder"


def architecture() -> str:
    """What this build runs on, for the file name.

    VTK publishes no universal2 wheel, so a release is two DMGs and
    the name is the only thing telling them apart on a download page.
    """
    machine = platform.machine()
    return "arm64" if machine == "arm64" else "x86_64"


def make(app: Path, into: Path, version: str) -> Path:
    """Write the DMG and return where it went."""
    out = into / f"Crystal-Builder-{version}-{architecture()}.dmg"
    out.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "staging"
        staging.mkdir()
        # copytree with symlinks preserved: a .app is full of them,
        # and PyInstaller 6 in particular symlinks between
        # Contents/Frameworks and Contents/Resources.  Following them
        # would both double the size and break the signature.
        shutil.copytree(app, staging / app.name, symlinks=True)
        (staging / "Applications").symlink_to("/Applications")

        subprocess.run(
            ["hdiutil", "create",
             "-volname", VOLUME,
             "-srcfolder", str(staging),
             "-ov", "-format", "UDZO",
             str(out)],
            check=True, capture_output=True, text=True)
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not 1 <= len(argv) <= 2:
        print('usage: makedmg.py "dist/Crystal Builder.app" [dist/]',
              file=sys.stderr)
        return 2

    app = Path(argv[0]).resolve()
    into = Path(argv[1]).resolve() if len(argv) > 1 else app.parent
    if not app.is_dir():
        print(f"{app} is not there", file=sys.stderr)
        return 1
    into.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bundle

    out = make(app, into, bundle.version())
    print(f"{out.name}  {out.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
