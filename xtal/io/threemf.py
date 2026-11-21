"""A 3MF of one object in several parts, each on its own extruder.

A two-color print is one body made of two meshes that meet at a
shared interface.  Written as two objects, a slicer arranges them
apart on the bed; written as one object of two *parts*, it keeps them
together and lets each part take its own filament.  The core 3MF spec
says how to make one object of several meshes (an object of type
``model`` whose ``<components>`` reference one mesh object each), but
not which extruder a mesh prints with: every slicer keeps that in a
side file of its own under ``Metadata/``.  Both side files are written,
and a slicer reads only its own.

What was copied from where (read 2026-11-21):

* ``3D/3dmodel.model``, ``[Content_Types].xml`` and ``_rels/.rels``
  follow Bambu Studio's exporter (``src/libslic3r/Format/bbs_3mf.cpp``,
  ``_add_content_types_file_to_archive``,
  ``_add_relationships_file_to_archive``,
  ``_add_object_components_to_stream``): the core 2015/02 namespace,
  ``unit="millimeter"``, a component with no ``p:path`` naming a mesh
  object in the same file, and the relationship target
  ``/3D/3dmodel.model``.  The production extension is not used, so
  every mesh sits in the root model.
* ``Metadata/model_settings.config`` (Bambu Studio, Orca Slicer) is
  ``_add_model_config_file_to_archive``: ``<config><object id=...>``
  keyed by the *composite* object's id, one ``<part id=...
  subtype="normal_part">`` per component whose ``id`` is the mesh
  object's, and ``<metadata key=... value=.../>`` entries.  The reader
  (``_handle_start_config_volume``, ``_generate_volumes_new``) takes a
  part's ``name`` and ``matrix`` and passes every other key -- here
  ``extruder`` -- to the part's config.  No ``matrix`` means identity.
* ``Metadata/Slic3r_PE_model.config`` (PrusaSlicer 2.x) is the legacy
  importer's (``src/slic3r-shared/src/Slic3r/Biz/Config/Legacy/
  3mf_legacy.cpp``): ``<object id=...>`` holding ``<volume firstid=
  lastid=>`` triangle ranges, metadata with ``type="object"`` or
  ``type="volume"`` (anything else is an error there).  That importer
  turns each component into an object of its own, so the entries are
  keyed by the *mesh* objects: PrusaSlicer 2.x loads two objects in
  place, each on its extruder, rather than one object of two parts.

The ``Application`` metadata names Crystal Builder and never a
slicer: Bambu Studio switches on its own project paths when it reads
``BambuStudio-``, and those expect files this writer does not make.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np

from xtal.io.atomic import replacing

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MODEL_PATH = "3D/3dmodel.model"
BAMBU_CONFIG = "Metadata/model_settings.config"
PRUSA_CONFIG = "Metadata/Slic3r_PE_model.config"

_CONTENT_TYPES = """\
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" \
ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" \
ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""

_RELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships \
xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" \
Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


@dataclass(frozen=True)
class Part:
    """One mesh of the object and the extruder (1-based) it prints
    with."""

    name: str
    vertices: np.ndarray
    triangles: np.ndarray
    extruder: int = 1


def _number(value: float) -> str:
    # Nine significant digits give back the float32 exactly, so a
    # part's vertices here are the same numbers as in its STL.
    return f"{value:.9g}"


def _mesh_xml(object_id: int, part: Part) -> list[str]:
    vertices = np.asarray(part.vertices, dtype=np.float32).reshape(-1, 3)
    triangles = np.asarray(part.triangles, dtype=np.int64).reshape(-1, 3)
    lines = [f'  <object id="{object_id}" name={quoteattr(part.name)} '
             'type="model">',
             "   <mesh>", "    <vertices>"]
    lines += [f'     <vertex x="{_number(x)}" y="{_number(y)}" '
              f'z="{_number(z)}"/>' for x, y, z in vertices.tolist()]
    lines += ["    </vertices>", "    <triangles>"]
    lines += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>'
              for a, b, c in triangles.tolist()]
    lines += ["    </triangles>", "   </mesh>", "  </object>"]
    return lines


def _model_xml(name: str, parts: Sequence[Part]) -> str:
    composite = len(parts) + 1
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<model unit="millimeter" xml:lang="en-US" '
             f'xmlns="{CORE_NS}">',
             ' <metadata name="Application">Crystal Builder</metadata>',
             f' <metadata name="Title">{_text(name)}</metadata>',
             " <resources>"]
    for index, part in enumerate(parts, start=1):
        lines += _mesh_xml(index, part)
    lines += [f'  <object id="{composite}" name={quoteattr(name)} '
              'type="model">', "   <components>"]
    lines += [f'    <component objectid="{index}"/>'
              for index in range(1, len(parts) + 1)]
    lines += ["   </components>", "  </object>", " </resources>",
              " <build>", f'  <item objectid="{composite}"/>', " </build>",
              "</model>", ""]
    return "\n".join(lines)


def _text(value: str) -> str:
    return quoteattr(value)[1:-1]


def _bambu_config(name: str, parts: Sequence[Part]) -> str:
    composite = len(parts) + 1
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>",
             f'  <object id="{composite}">',
             f'    <metadata key="name" value={quoteattr(name)}/>',
             # The object's own extruder is what a part with none
             # falls back to; every part here names its own.
             f'    <metadata key="extruder" '
             f'value="{parts[0].extruder}"/>']
    for index, part in enumerate(parts, start=1):
        lines += [f'    <part id="{index}" subtype="normal_part">',
                  f'      <metadata key="name" '
                  f'value={quoteattr(part.name)}/>',
                  f'      <metadata key="extruder" '
                  f'value="{part.extruder}"/>',
                  "    </part>"]
    lines += ["  </object>", "</config>", ""]
    return "\n".join(lines)


def _prusa_config(parts: Sequence[Part]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    for index, part in enumerate(parts, start=1):
        last = len(np.asarray(part.triangles).reshape(-1, 3)) - 1
        lines += [f' <object id="{index}" instances_count="1">',
                  f'  <metadata type="object" key="name" '
                  f'value={quoteattr(part.name)}/>',
                  f'  <volume firstid="0" lastid="{last}">',
                  f'   <metadata type="volume" key="name" '
                  f'value={quoteattr(part.name)}/>',
                  '   <metadata type="volume" key="volume_type" '
                  'value="ModelPart"/>',
                  f'   <metadata type="volume" key="extruder" '
                  f'value="{part.extruder}"/>',
                  "  </volume>", " </object>"]
    lines += ["</config>", ""]
    return "\n".join(lines)


def write_3mf(path, parts: Sequence[Part], name: str = "") -> Path:
    """Write ``parts`` as one object of that many parts.

    A part with no triangles is left out: an object with an empty mesh
    is invalid 3MF, and a slicer refuses the whole file over it.
    ``name`` is the object's; it defaults to the file's stem.
    """
    path = Path(path)
    name = name or path.stem
    parts = [part for part in parts
             if np.asarray(part.triangles).size]
    if not parts:
        raise ValueError("a 3MF needs at least one part with triangles")
    files = {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _RELS,
        MODEL_PATH: _model_xml(name, parts),
        BAMBU_CONFIG: _bambu_config(name, parts),
        PRUSA_CONFIG: _prusa_config(parts),
    }
    with replacing(path) as partial:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
            for member, text in files.items():
                out.writestr(member, text.encode("utf-8"))
    return path


__all__ = ["Part", "write_3mf"]
