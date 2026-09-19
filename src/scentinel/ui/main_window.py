"""Application shell: menus, panels, project lifecycle, and status reporting.

The window owns the current :class:`~scentinel.core.project.Project` and keeps
it in sync with the two editing surfaces — :class:`SetupPanel` (forms) and
:class:`ViewportWidget` (sensor clicks). Solver execution is not wired here:
:attr:`MainWindow.run_requested` carries the fully resolved project so a worker
can be attached later without touching the UI.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QWidget,
)

from scentinel import __version__
from scentinel.core.geometry import BinGeometry
from scentinel.core.project import FILE_FILTER, SUFFIX, Project, load_project, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.i18n import LANGUAGES, Translator
from scentinel.ui.results_panel import ResultsPanel, SensorReading
from scentinel.ui.setup_panel import SetupPanel
from scentinel.ui.solver_worker import RunOutcome, SolverThread, SolverWorker
from scentinel.ui.viewport import ViewportWidget

IMAGE = "opencfd/openfoam-default:2512"

STYLE_SHEET = """
QMainWindow { background: #ffffff; }
QGroupBox {
    border: 1px solid #d6dbd8;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #1b4332; }
QLabel#resultsTitle, QLabel#viewportTitle { font-weight: 600; color: #1b4332; }
QLabel#actualFillLabel { color: #1b4332; }
QStatusBar QLabel { color: #4b5563; }
"""


class MainWindow(QMainWindow):
    """Scentinel main window."""

    run_requested = Signal(object)  # Project
    cancel_requested = Signal()
    locale_changed = Signal(str)

    def __init__(
        self,
        translator: Translator,
        project: Project | None = None,
        path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._t = translator
        self._project = project or _default_project()
        self._path = path
        self._dirty = False
        self._loading = False
        self._status_key: str | None = None
        self._status_args: dict[str, object] = {}
        self._solver_available, self._solver_note = _probe_solver()
        self._solver_thread: SolverThread | None = None
        self._run_counter = 0

        self._build_panels()
        self._build_menus()
        self._build_status_bar()
        self.setStyleSheet(STYLE_SHEET)

        self._t.changed.connect(self.retranslate)
        self._viewport.sensor_added.connect(lambda _sensor: self._status_flash("status.sensors"))
        self._apply_project(self._project)
        self._status_flash("status.ready")
        self.retranslate()

    # -- construction --------------------------------------------------------

    def _build_panels(self) -> None:
        self._setup_panel = SetupPanel(self._t)
        self._viewport = ViewportWidget()
        self._results_panel = ResultsPanel(self._t)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._setup_panel)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._results_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 720, 380])
        self.setCentralWidget(splitter)

        self._setup_panel.changed.connect(self._on_setup_changed)
        self._viewport.sensors_changed.connect(self._on_sensors_changed)
        self._viewport.cursor_moved.connect(self._on_cursor_moved)
        self._results_panel.cancel_requested.connect(self.cancel_run)
        self._results_panel.run_requested.connect(self.start_run)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("")
        self._file_menu = file_menu
        self._action_new = _action(file_menu, QKeySequence.StandardKey.New, self.new_project)
        self._action_open = _action(file_menu, QKeySequence.StandardKey.Open, self.open_project)
        self._action_save = _action(file_menu, QKeySequence.StandardKey.Save, self.save_project)
        self._action_save_as = _action(file_menu, QKeySequence.StandardKey.SaveAs, self.save_project_as)
        file_menu.addSeparator()
        self._action_export = _action(file_menu, None, self.export_csv)
        self._action_export.setEnabled(False)
        file_menu.addSeparator()
        self._action_quit = _action(file_menu, QKeySequence.StandardKey.Quit, self.close)

        run_menu = self.menuBar().addMenu("")
        self._run_menu = run_menu
        self._action_run = _action(run_menu, "F5", self.start_run)
        self._action_run.setEnabled(self._solver_available)
        self._action_cancel = _action(run_menu, "Shift+F5", self.cancel_run)

        view_menu = self.menuBar().addMenu("")
        self._view_menu = view_menu
        self._language_menu = view_menu.addMenu("")
        group = QActionGroup(self)
        group.setExclusive(True)
        self._language_actions: dict[str, QAction] = {}
        for code, label in LANGUAGES.items():
            action = QAction(label, self, checkable=True)
            action.setChecked(code == self._t.locale)
            action.triggered.connect(lambda _checked, value=code: self._set_locale(value))
            group.addAction(action)
            self._language_menu.addAction(action)
            self._language_actions[code] = action
        view_menu.addSeparator()
        self._action_fit = _action(view_menu, "Ctrl+0", self._viewport.fit_to_window)
        self._action_reset = _action(view_menu, "Ctrl+Shift+0", self._viewport.reset_view)

        help_menu = self.menuBar().addMenu("")
        self._help_menu = help_menu
        self._action_about = _action(help_menu, None, self._show_about)

        self._results_panel.export_requested.connect(self.export_csv)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self._status_label = QLabel()
        self._sensor_label = QLabel()
        self._cursor_label = QLabel()
        self._solver_label = QLabel()
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._cursor_label)
        bar.addPermanentWidget(self._sensor_label)
        bar.addPermanentWidget(self._solver_label)

    # -- accessors -----------------------------------------------------------

    def project(self) -> Project:
        return self._project

    def project_path(self) -> Path | None:
        return self._path

    def setup_panel(self) -> SetupPanel:
        return self._setup_panel

    def viewport(self) -> ViewportWidget:
        return self._viewport

    def results_panel(self) -> ResultsPanel:
        return self._results_panel

    def is_dirty(self) -> bool:
        return self._dirty

    def solver_available(self) -> bool:
        return self._solver_available

    # -- project lifecycle ---------------------------------------------------

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._path = None
        self._apply_project(_default_project())
        self._results_panel.clear()
        self._dirty = False
        self._status_flash("status.ready")

    def open_project(self, path: Path | None = None) -> None:
        if not self._confirm_discard():
            return
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self, self._t.t("menu.file.open"), str(self._start_dir()), FILE_FILTER
            )
            if not chosen:
                return
            path = Path(chosen)
        try:
            project = load_project(path)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(
                self, self._t.t("error.open_failed"), f"{path}\n\n{error}"
            )
            return
        self._apply_project(project, path=path)
        self._results_panel.clear()
        self._dirty = False
        self._status_flash("log.opened", path=path.name)

    def save_project(self) -> bool:
        if self._path is None:
            return self.save_project_as()
        return self._write_project(self._path)

    def save_project_as(self) -> bool:
        suggested = self._path or (self._start_dir() / f"{self._project.name}{SUFFIX}")
        chosen, _ = QFileDialog.getSaveFileName(
            self, self._t.t("menu.file.save_as"), str(suggested), FILE_FILTER
        )
        if not chosen:
            return False
        path = Path(chosen)
        if path.suffix != SUFFIX:
            path = path.with_suffix(SUFFIX)
        if path.exists() and not self._confirm_overwrite(path):
            return False
        return self._write_project(path)

    def export_csv(self) -> None:
        readings = self._results_panel.readings()
        if not readings:
            return
        suggested = self._start_dir() / f"{self._project.name}-sensors.csv"
        chosen, _ = QFileDialog.getSaveFileName(
            self, self._t.t("menu.file.export_csv"), str(suggested), "CSV (*.csv);;All files (*)"
        )
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            self._results_panel.export_results_csv(path)
        except OSError as error:
            QMessageBox.warning(self, self._t.t("error.export_failed"), str(error))
            return
        self._status_flash("log.exported", path=path.name)

    def _write_project(self, path: Path) -> bool:
        self._project.name = self._project.name or path.stem
        try:
            save_project(self._project, path)
        except OSError as error:
            QMessageBox.warning(self, self._t.t("error.save_failed"), str(error))
            return False
        self._path = path
        self._dirty = False
        self._refresh_title()
        self._status_flash("log.saved", path=path.name)
        return True

    def _apply_project(self, project: Project, path: Path | None = None) -> None:
        self._loading = True
        try:
            self._project = project
            if path is not None:
                self._path = path
            self._setup_panel.set_values(project.geometry, project.scenario)
            self._viewport.set_geometry(project.geometry)
            self._viewport.set_sensors(project.sensors)
        finally:
            self._loading = False
        self._refresh_title()
        self._refresh_counters()

    # -- solver --------------------------------------------------------------

    def is_running(self) -> bool:
        return self._solver_thread is not None and self._solver_thread.isRunning()

    def start_run(self) -> bool:
        """Launch the solver for the current project. Returns False if blocked."""
        if self.is_running():
            return False
        if not self._project.sensors:
            self._status_flash("run.needs_sensor")
            return False
        if not self._project.scenario.gas_sources:
            self._status_flash("run.needs_gas")
            return False
        if not self._solver_available:
            self._status_flash("run.blocked")
            return False

        self._run_counter += 1
        run_dir = _runs_root(self._path) / f"run-{self._run_counter:03d}"
        self._results_panel.clear()
        self._results_panel.set_running(True)
        self._set_running_ui(True)
        self._status_flash("status.running")

        worker = SolverWorker(self._project, run_dir)
        thread = SolverThread(worker)
        worker.log_message.connect(self._results_panel.append_log)
        worker.progress.connect(self._on_run_progress)
        worker.finished.connect(self._on_run_finished)
        thread.finished.connect(thread.deleteLater)
        self._solver_thread = thread
        thread.start()
        return True

    def cancel_run(self) -> None:
        if self._solver_thread is not None and self._solver_thread.isRunning():
            self._solver_thread.cancel()
            self._status_flash("status.cancelled")

    def _on_run_progress(self, percent: int, stage: str) -> None:
        self._status_label.setText(f"{self._t.t('status.running')} {percent}% ({stage})")

    def _on_run_finished(self, outcome: RunOutcome) -> None:
        self._set_running_ui(False)
        self._results_panel.set_running(False)
        self._solver_thread = None

        if outcome.readings:
            self._results_panel.set_results(
                [
                    SensorReading(
                        sensor_id=reading.sensor_id,
                        x=reading.x,
                        y=reading.y,
                        values={gas: value * 1e6 for gas, value in reading.values.items()},
                    )
                    for reading in outcome.readings
                ]
            )

        if outcome.ok:
            self._status_flash("status.done")
            return
        if outcome.exit_code == -2:
            self._status_flash("status.cancelled")
            return
        self._status_flash("status.error")
        if outcome.error:
            self._results_panel.append_log(f"ERROR: {outcome.error}")

    def _set_running_ui(self, running: bool) -> None:
        self._action_run.setEnabled(not running)
        self._setup_panel.setEnabled(not running)
        self._results_panel.set_running(running)

    # -- signals from the editing surfaces -----------------------------------

    def _on_setup_changed(self, geom: BinGeometry, scenario: Scenario) -> None:
        if self._loading:
            return
        self._project.geometry = geom
        self._project.scenario = scenario
        self._viewport.set_geometry(geom)
        self._mark_dirty()

    def _on_sensors_changed(self) -> None:
        if self._loading:
            return
        self._project.sensors = self._viewport.sensors()
        self._mark_dirty()
        self._refresh_counters()

    def _on_cursor_moved(self, x: float, y: float) -> None:
        self._cursor_label.setText(self._t.t("viewport.cursor", x=x, y=y))

    def _set_locale(self, locale: str) -> None:
        self._t.set_locale(locale)
        self.locale_changed.emit(locale)

    # -- status --------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            self._refresh_title()

    def _refresh_title(self) -> None:
        name = self._path.name if self._path else self._project.name
        marker = " •" if self._dirty else ""
        self.setWindowTitle(f"{self._t.t('app.title')} — {name}{marker}")

    def _refresh_counters(self) -> None:
        self._sensor_label.setText(
            self._t.t("status.sensors", count=len(self._project.sensors))
        )

    def _status_flash(self, key: str, **kwargs: object) -> None:
        self._status_key = key
        self._status_args = kwargs
        self._status_label.setText(self._t.t(key, **kwargs))

    def _refresh_solver_note(self) -> None:
        if self._solver_available:
            self._solver_label.setText(f"OpenFOAM · {IMAGE}")
            self._solver_label.setStyleSheet("color: #15803d;")
            self._solver_label.setToolTip("")
        else:
            self._solver_label.setText(self._t.t("run.blocked"))
            self._solver_label.setStyleSheet("color: #b45309;")
            self._solver_label.setToolTip(self._solver_note)

    def _refresh_status(self) -> None:
        """Re-render the status line in the active language."""
        if self._status_key is None:
            self._status_label.setText(self._t.t("status.ready"))
        else:
            self._status_label.setText(self._t.t(self._status_key, **self._status_args))

    # -- i18n ----------------------------------------------------------------

    def retranslate(self) -> None:
        t = self._t.t
        self._file_menu.setTitle(t("menu.file"))
        self._action_new.setText(t("menu.file.new"))
        self._action_open.setText(t("menu.file.open"))
        self._action_save.setText(t("menu.file.save"))
        self._action_save_as.setText(t("menu.file.save_as"))
        self._action_export.setText(t("menu.file.export_csv"))
        self._action_quit.setText(t("menu.file.quit"))
        self._view_menu.setTitle(t("menu.view"))
        self._language_menu.setTitle(t("menu.view.language"))
        self._action_fit.setText(t("menu.view.fit"))
        self._action_reset.setText(t("menu.view.reset"))
        self._help_menu.setTitle(t("menu.help"))
        self._action_about.setText(t("menu.help.about"))
        self._run_menu.setTitle(t("menu.run"))
        self._action_run.setText(t("action.run"))
        self._action_cancel.setText(t("action.cancel"))
        self._action_run.setEnabled(self._solver_available and not self.is_running())
        self._viewport.setToolTip(t("viewport.hint"))
        for code, action in self._language_actions.items():
            action.setChecked(code == self._t.locale)
        self._refresh_title()
        self._refresh_counters()
        self._refresh_solver_note()
        self._refresh_status()

    # -- dialogs -------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            self._t.t("about.title"),
            self._t.t("about.text", version=__version__),
        )

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            self._t.t("dialog.unsaved.title"),
            self._t.t("dialog.unsaved.text", name=self._path.name if self._path else self._project.name),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def _confirm_overwrite(self, path: Path) -> bool:
        answer = QMessageBox.question(
            self,
            self._t.t("dialog.overwrite.title"),
            self._t.t("dialog.overwrite.text", name=path.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _start_dir(self) -> Path:
        if self._path is not None:
            return self._path.parent
        return Path.cwd()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def _default_project() -> Project:
    return Project(name="Untitled", geometry=BinGeometry(), scenario=Scenario())


def _runs_root(project_path: Path | None) -> Path:
    """Where run directories go: beside the project file, else in the cwd."""
    base = project_path.parent if project_path is not None else Path.cwd()
    return base / "runs"


def _action(menu, shortcut: QKeySequence.StandardKey | str | None, slot) -> QAction:
    action = QAction(menu)
    if shortcut is not None:
        action.setShortcut(shortcut)
    action.triggered.connect(lambda _checked=False: slot())
    menu.addAction(action)
    return action


def _probe_solver() -> tuple[bool, str]:
    """Report whether the OpenFOAM container is reachable; never raises."""
    if shutil.which("podman") is None:
        return False, "podman is not installed"
    return True, ""
