"""Hint text and warnings that read in both themes.

The Qt chrome follows the system already; three styles did not, and
they were literals in fifty places -- dark amber on a dark panel,
a cream box as a light patch in a dark window, and `palette(mid)`
hint text nearly the colour of the background it sat on.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from pathlib import Path  # noqa: E402

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport.view_settings import (  # noqa: E402
    BACKGROUNDS,
    FOLLOW_THE_SYSTEM,
    THEME_BACKGROUNDS,
)
from xtalapp.widgets.tone import (  # noqa: E402
    HINT,
    WARNING,
    WARNING_BOX,
    is_dark,
    retone,
    set_tone,
    style,
)


def _dark() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, "#1e1e1e")
    palette.setColor(QPalette.WindowText, "#f0f0f0")
    return palette


def _light() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, "#ececec")
    palette.setColor(QPalette.WindowText, "#101010")
    return palette


def test_a_light_window_keeps_the_colours_it_had():
    """The literals these replaced, exactly."""
    assert style(WARNING, _light()) == "color: #8a5a00;"
    assert style(WARNING_BOX, _light()) == (
        "color: #8a5a00; background: #fdf3e0; padding: 5px;")


def test_a_dark_window_gets_amber_that_reads_on_it():
    assert style(WARNING, _dark()) != style(WARNING, _light())
    assert style(WARNING_BOX, _dark()) != style(WARNING_BOX, _light())
    assert is_dark(_dark()) and not is_dark(_light())


def test_a_hint_is_the_text_colour_faded_not_a_fixed_grey(qapp):
    """`palette(mid)` on the macOS dark palette is nearly the
    background, which is how the sentence explaining Save File became
    invisible."""
    assert "240, 240, 240" in style(HINT, _dark())      # not grey
    assert "16, 16, 16" in style(HINT, _light())


def test_padding_survives_a_warning_clearing(qapp):
    """A box that loses its padding when its warning goes jumps under
    the cursor."""
    assert style(None, _light(), padding=4) == "padding: 4px;"
    assert style(WARNING_BOX, _light(), padding=4).endswith(
        "padding: 4px;")


def test_a_toned_widget_is_restyled_when_the_theme_changes(qapp):
    """Starts from a light palette on purpose.  Starting from whatever
    the machine had made this fail on any Mac already in dark mode:
    "before" and "after" were the same amber, and CI -- always light --
    never saw it."""
    original = qapp.palette()
    qapp.setPalette(_light())
    try:
        label = QLabel()
        set_tone(label, WARNING_BOX, padding=6)
        light = label.styleSheet()

        qapp.setPalette(_dark())
        assert retone(label) == 1
        assert label.styleSheet() != light
        assert "padding: 6px;" in label.styleSheet()
    finally:
        qapp.setPalette(original)


def test_no_widget_styles_a_warning_by_hand(qapp):
    """The whole point: one place decides what a warning looks like."""
    offenders = []
    for path in sorted(Path("xtalapp").rglob("*.py")):
        if path.name == "tone.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "#8a5a00" in text or "#fdf3e0" in text \
                or "palette(mid)" in text:
            offenders.append(path.name)
    assert offenders == []


# ------------------------------------------------- the viewport, too

@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Tone{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


def test_a_new_structure_follows_the_system_background(window,
                                                       rutile_cif):
    document = window.open_path(rutile_cif)

    assert document.view.background_follows_theme
    assert tuple(document.view.background) == THEME_BACKGROUNDS[is_dark()]


def test_choosing_a_colour_stops_it_following(window, rutile_cif):
    document = window.open_path(rutile_cif)

    window.set_background("paper")

    assert not document.view.background_follows_theme
    assert tuple(document.view.background) == BACKGROUNDS["paper"]


def test_following_again_is_one_menu_entry(window, rutile_cif):
    document = window.open_path(rutile_cif)
    window.set_background("black")

    window.set_background(FOLLOW_THE_SYSTEM)

    assert document.view.background_follows_theme


def test_a_theme_change_repaints_what_follows_it(window, rutile_cif,
                                                 monkeypatch):
    document = window.open_path(rutile_cif)
    monkeypatch.setattr("xtalapp.mainwindow.theme_background",
                        lambda: (1, 2, 3))

    window._follow_theme()

    assert tuple(document.view.background) == (1, 2, 3)


def test_a_theme_change_leaves_a_chosen_colour_alone(window,
                                                     rutile_cif,
                                                     monkeypatch):
    """An explicit choice is not a thing to overwrite when the sun
    goes down."""
    document = window.open_path(rutile_cif)
    window.set_background("black")
    monkeypatch.setattr("xtalapp.mainwindow.theme_background",
                        lambda: (1, 2, 3))

    window._follow_theme()

    assert tuple(document.view.background) == BACKGROUNDS["black"]


def test_a_project_keeps_whether_it_followed(window, rutile_cif,
                                             tmp_path):
    document = window.open_path(rutile_cif)
    window.set_background("slate")
    path = document.save(tmp_path / "kept.xtalproj")
    window.close_document(0)

    reopened = window.open_path(path)

    assert not reopened.view.background_follows_theme
    assert tuple(reopened.view.background) == BACKGROUNDS["slate"]
