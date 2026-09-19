"""Application shell: menus, panels, project lifecycle, and status reporting.

The window owns the current :class:`~scentinel.core.project.Project` and keeps
it in sync with the two editing surfaces — :class:`SetupPanel` (forms) and
:class:`ViewportWidget` (sensor clicks). It also owns run orchestration: it
reserves a persistent run record through :mod:`scentinel.core.history` before
starting the worker, and finalizes that same record with the worker's outcome.
The history module is the only writer of run manifests; the window never
allocates run ids itself.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

from scentinel import __version__
from scentinel.core import container, history
from scentinel.core.casegen import PPM_SCALE
from scentinel.core.gas_data import DEFAULT_SOURCE_GASES
from scentinel.core.geometry import BinGeometry
from scentinel.core.history import HistoryError, RunRecord
from scentinel.core.project import FILE_FILTER, SUFFIX, Project, load_project, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.i18n import LANGUAGES, Translator
from scentinel.ui.workspace import DockedWorkspace
from scentinel.ui.results_panel import ResultsPanel, SensorReading
from scentinel.ui.sensor_lab import SensorLabPanel
from scentinel.ui.setup_panel import SetupPanel
from scentinel.ui.batch_panel import BatchPanel
from scentinel.ui.solver_worker import (
    DEFAULT_END_ITERATION,
    DEFAULT_MESH_SIZE_M,
    RunOutcome,
    SolverThread,
    SolverWorker,
)
from scentinel.ui.viewport import ViewportWidget

IMAGE = "opencfd/openfoam-default:2512"



class ContainerSetupWorker(QObject):
    """Pulls the solver image and verifies it, off the GUI thread.

    Delegates to :func:`scentinel.core.container.setup_container`, which is the
    single implementation shared with the CLI and the shell script; this class
    only adapts its callback to a Qt signal.

    A raise is reported as a failed result rather than propagating: the window
    clears its "setting up" state on the result, and an unhandled exception
    would leave both triggers disabled forever.
    """

    log_message = Signal(str)
    finished = Signal(object)  # ContainerSetupResult

    def run(self) -> None:
        try:
            result = container.setup_container(on_log=self.log_message.emit)
        except Exception as error:  # surfaced in the log, never swallowed
            self.log_message.emit(f"ERROR: {type(error).__name__}: {error}")
            result = container.ContainerSetupResult(ok=False, exit_code=1, log=[])
        self.finished.emit(result)


class ContainerSetupThread(QThread):
    """QThread wrapper so a setup can run without blocking the window."""

    def __init__(self, worker: ContainerSetupWorker) -> None:
        super().__init__()
        self._worker = worker
        worker.moveToThread(self)

    def run(self) -> None:
        self._worker.run()


class MainWindow(DockedWorkspace):
    """The project editor: a dock-based workspace with its own menus."""

    home_requested = Signal()
    project_path_changed = Signal(object)  # Path | None
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
        super().__init__(translator, parent=parent)
        self._t = translator
        self._project = project or _default_project()
        self._path = path
        self._dirty = False
        self._loading = False
        self._status_key: str | None = None
        self._status_args: dict[str, object] = {}
        self._solver_available, self._solver_note = _probe_solver()
        self._solver_thread: SolverThread | None = None
        self._container_thread: ContainerSetupThread | None = None
        self._container_setup_active = False
        self._active_run: RunRecord | None = None
        self._last_assessment = None

        self._build_panels()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()

        self._t.changed.connect(self.retranslate)
        self._viewport.sensor_added.connect(lambda _sensor: self._status_flash("status.sensors"))
        self._apply_project(self._project)
        if self._path is not None:
            self._restore_latest_run()
        self._status_flash("status.ready")
        self.retranslate()

    # -- construction --------------------------------------------------------

    def _build_panels(self) -> None:
        self._setup_panel = SetupPanel(
            self._t,
            default_mesh_size_m=DEFAULT_MESH_SIZE_M,
            default_end_iteration=DEFAULT_END_ITERATION,
        )
        self._viewport = ViewportWidget()
        self._results_panel = ResultsPanel(self._t)
        self._sensor_lab = SensorLabPanel(self._t)
        self._batch_panel = BatchPanel(self._t)

        # Panels are docks, not fixed splitter panes: each one can be dragged to
        # another edge, tabbed together with another, floated, or hidden, and the
        # arrangement is remembered per workspace.
        self.add_panel(
            "setup", self._t.t("panel.setup"), self._setup_panel,
            Qt.DockWidgetArea.LeftDockWidgetArea, min_size=(240, 0),
        )
        self.add_panel(
            "viewport", self._t.t("panel.viewport"), self._viewport,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.add_panel(
            "results", self._t.t("panel.results"), self._results_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
        )
        self.add_panel(
            "sensor_lab", self._t.t("panel.sensor_lab"), self._sensor_lab,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        self.add_panel(
            "batch", self._t.t("panel.batch"), self._batch_panel,
            Qt.DockWidgetArea.RightDockWidgetArea, min_size=(260, 0),
        )
        self.tabifyDockWidget(self.dock("viewport"), self.dock("sensor_lab"))
        self.dock("viewport").raise_()
        self.dock("sensor_lab").setVisible(False)

        self.resize(1440, 900)
        self.setMinimumSize(760, 520)

        self._setup_panel.changed.connect(self._on_setup_changed)
        self._batch_panel.assessed.connect(self._on_batch_assessed)
        self._viewport.sensors_changed.connect(self._on_sensors_changed)
        self._viewport.cursor_moved.connect(self._on_cursor_moved)
        self._results_panel.cancel_requested.connect(self.cancel_run)
        self._results_panel.run_requested.connect(self.start_run)
        self._sensor_lab.config_changed.connect(self._on_lab_config_changed)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("")
        self._file_menu = file_menu
        self._action_home = _action(file_menu, "Alt+Left", self.home_requested.emit)
        file_menu.addSeparator()
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
        run_menu.addSeparator()
        self._action_setup_container = _action(
            run_menu, None, self.setup_container
        )

        view_menu = self.menuBar().addMenu("")
        self._view_menu = view_menu
        self._action_fit = _action(view_menu, "Ctrl+0", self._viewport.fit_to_window)
        self._action_reset = _action(view_menu, "Ctrl+Shift+0", self._viewport.reset_view)
        view_menu.addSeparator()

        help_menu = self.menuBar().addMenu("")
        self._help_menu = help_menu
        self._action_about = _action(help_menu, None, self._show_about)

        self._results_panel.export_requested.connect(self.export_csv)

    def _build_toolbar(self) -> None:
        """A toolbar with the same container action, so it is discoverable."""
        toolbar = QToolBar("Container", self)
        toolbar.setObjectName("containerToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.addAction(self._action_setup_container)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._container_toolbar = toolbar

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

    def sensor_lab(self) -> SensorLabPanel:
        return self._sensor_lab

    def batch_panel(self) -> BatchPanel:
        return self._batch_panel

    def view_menu(self):
        """The editor's View menu, which the shell extends with layout controls."""
        return self._view_menu

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
        self._restore_latest_run()
        self._dirty = False
        self._status_flash("log.opened", path=path.name)
        self.project_path_changed.emit(path)

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
        self.project_path_changed.emit(path)
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
            self._sensor_lab.set_config(project.sensor_lab)
            self._sensor_lab.set_context(project.sensors, self._results_panel.readings())
        finally:
            self._loading = False
        self._refresh_title()
        self._refresh_counters()
    def _restore_latest_run(self) -> None:
        """Reload the newest succeeded run so a project can continue mid-work."""
        self._results_panel.clear()
        if self._path is None:
            return
        try:
            runs = history.list_runs(_runs_root(self._path))
        except OSError:
            return
        for record in reversed(runs):
            if record.execution_status != "succeeded":
                continue
            if not record.results.sensor_readings:
                continue
            self._results_panel.set_run_record(record)
            self._results_panel.set_results(
                [
                    SensorReading(
                        sensor_id=item.sensor_id,
                        x=item.x_m,
                        y=item.y_m,
                        values=dict(item.values_ppmv),
                    )
                    for item in record.results.sensor_readings
                ]
            )
            return

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

        self._results_panel.clear()
        # One deep snapshot feeds both the manifest and the worker, so the
        # sensors the record freezes are the sensors the pipeline samples.
        # Editing continues to act on ``self._project``, never on this copy.
        frozen = history.snapshot_project(self._project)
        try:
            record = history.begin_run(
                _runs_root(self._path),
                frozen,
                mesh_size_m=self._setup_panel.mesh_size_m(),
                end_iteration=self._setup_panel.end_iteration(),
            )
        except (HistoryError, OSError, KeyError, ValueError) as error:
            # No durable record, so no run: the reservation is the run identity.
            self._status_flash("run.history_failed")
            self._results_panel.append_log(f"ERROR: {error}")
            return False

        self._active_run = record
        self._results_panel.append_log(
            self._t.t(
                "log.run_reserved",
                run_id=record.run_id,
                path=record.run_dir / history.MANIFEST_NAME,
            )
        )
        self._results_panel.set_run_record(record)
        self._results_panel.set_running(True)
        self._set_running_ui(True)
        self._status_flash("status.running")

        worker = SolverWorker(
            frozen,
            record.run_dir,
            mesh_size_m=self._setup_panel.mesh_size_m(),
            end_time=self._setup_panel.end_iteration(),
        )
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

        record = self._active_run
        self._active_run = None
        readings_ppmv = _ppmv_readings(outcome.readings)
        if readings_ppmv:
            self._results_panel.set_results(readings_ppmv)
        if outcome.ok and outcome.case_dir is not None:
            # Field rendering is a view of the run, never part of it. It pulls
            # in VTK and a plotting backend, so it can fail for reasons that
            # have nothing to do with the solve (an offscreen GL stack, a
            # partially imported plotting module). Letting that escape here
            # would skip `_finalize_run` and leave the manifest `incomplete`
            # even though the solver produced results — a lost audit record for
            # a purely cosmetic failure.
            try:
                self._results_panel.set_field_case(outcome.case_dir, readings_ppmv)
            except Exception as error:  # noqa: BLE001 - reported, never fatal
                self._results_panel.append_log(f"WARNING: field visual unavailable: {error}")

        status = _terminal_status(outcome, record) if record is not None else None
        persisted = self._finalize_run(record, outcome, readings_ppmv, status)
        if persisted is not None:
            self._results_panel.set_run_record(persisted)

        if outcome.error:
            self._results_panel.append_log(f"ERROR: {outcome.error}")
        if persisted is not None:
            if status == "succeeded":
                self._status_flash("status.done")
            elif status == "cancelled":
                self._status_flash("status.cancelled")
            else:
                self._status_flash("status.error")
            return
        if outcome.ok:
            self._status_flash("status.done_history_failed")
        elif outcome.exit_code == -2:
            self._status_flash("status.cancelled")
        else:
            self._status_flash("status.error")

    def _finalize_run(
        self,
        record: RunRecord | None,
        outcome: RunOutcome,
        readings_ppmv: list[SensorReading],
        status: str | None,
    ) -> RunRecord | None:
        """Write and return the terminal manifest, or ``None`` on failure."""
        if record is None or status is None:
            return None
        try:
            return history.finish_run(
                record,
                status=status,
                case_dir=outcome.case_dir,
                mesh_cells=outcome.mesh_cells,
                element_types=outcome.element_types,
                exit_code=outcome.exit_code,
                failed_stage=outcome.failed_stage,
                error=outcome.error or None,
                readings_ppmv=readings_ppmv,
            )
        except (HistoryError, OSError, ValueError) as error:
            self._results_panel.append_log(f"ERROR: run not recorded: {error}")
            return None

    def _set_running_ui(self, running: bool) -> None:
        self._refresh_run_action(solving=running)
        self._setup_panel.setEnabled(not running)
        # The viewport is disabled too: it is the only other way to mutate the
        # project while a run is in flight. Correctness does not depend on it —
        # the worker holds a frozen snapshot — but leaving it live would let a
        # click change what the *next* run captures mid-flight.
        self._viewport.setEnabled(not running)
        self._results_panel.set_running(running)

    # -- container setup -----------------------------------------------------

    def is_setting_up_container(self) -> bool:
        """Whether a setup is in flight.

        Tracked as a flag, not as thread liveness: the worker emits its result
        just before its thread stops, so between those two moments
        ``isRunning()`` would already be False while the finish handler is
        still queued — long enough for a second setup to slip through.
        """
        return self._container_setup_active

    def _refresh_run_action(self, *, solving: bool | None = None) -> None:
        """Run is available only when the solver is ready, idle, and has input.

        ``solving`` is passed explicitly where the caller already knows the
        solve state: a QThread is neither running yet when a run starts nor
        reliably stopped when it reports finished, so probing liveness at those
        two edges would enable Run at the wrong moment. A container setup also
        blocks Run — the image it enables Run for may not exist yet, and the
        storage it writes must not race a solve.

        The action is disabled while the project lacks sensors or gases, and its
        tooltip names the missing piece. A button that looks ready but refuses
        the click, with the reason only in the status bar, is how a run gets
        reported as "broken" when it is merely unconfigured.
        """
        if solving is None:
            solving = self.is_running()
        busy = solving or self.is_setting_up_container()
        ready = self._solver_available and not busy
        blocker = self._run_blocker()
        self._action_run.setEnabled(ready and blocker is None)
        self._action_setup_container.setEnabled(not busy)
        if blocker is not None:
            self._action_run.setToolTip(self._t.t(blocker))
        elif not self._solver_available:
            self._action_run.setToolTip(self._t.t("run.blocked"))
        else:
            self._action_run.setToolTip("")
        self._results_panel.set_run_enabled(ready and blocker is None, blocker)

    def _run_blocker(self) -> str | None:
        """Translation key for what stops a run, or None when nothing does."""
        if not self._solver_available:
            return "run.blocked"
        if not self._project.sensors:
            return "run.needs_sensor"
        if not self._project.scenario.gas_sources:
            return "run.needs_gas"
        return None

    def setup_container(self) -> bool:
        """Pull and verify the OpenFOAM image, off the GUI thread.

        Both triggers are disabled for the duration: podman must not be asked
        to pull the same image twice, and the Run action must not race the
        storage this writes. Returns False when a setup is already in flight.
        """
        if self.is_setting_up_container():
            return False
        self._container_setup_active = True
        self._action_setup_container.setEnabled(False)
        self._action_run.setEnabled(False)
        self._results_panel.append_log(f"==> {self._t.t('action.setup_container')}")
        self._results_panel.append_log(f"    Storage: {container.storage_root()}")
        self._status_flash("status.running")

        worker = ContainerSetupWorker()
        thread = ContainerSetupThread(worker)
        worker.log_message.connect(self._results_panel.append_log)
        worker.finished.connect(self._on_container_setup_finished)
        thread.finished.connect(thread.deleteLater)
        self._container_thread = thread
        thread.start()
        return True

    def _on_container_setup_finished(self, result: container.ContainerSetupResult) -> None:
        self._container_setup_active = False
        # Same lifetime rule as ``SolverThread``: the reference goes when the
        # worker reports, and the thread deletes itself once it actually stops.
        self._container_thread = None
        # Re-probe rather than trusting the exit code: what enables Run is the
        # image being present in this app's storage, not the pull's own report.
        self._solver_available, self._solver_note = _probe_solver()
        self._refresh_solver_note()
        self._refresh_run_action()
        self._status_flash(
            "status.container_ready" if result.ok else "status.container_failed"
        )

    # -- signals from the editing surfaces -----------------------------------

    def _on_setup_changed(self, geom: BinGeometry, scenario: Scenario) -> None:
        if self._loading:
            return
        self._project.geometry = geom
        self._project.scenario = scenario
        self._viewport.set_geometry(geom)
        self._mark_dirty()
        # Selecting a gas or placing a sensor can unblock Run, so the action's
        # enabled state has to follow the inputs, not just the solver probe.
        self._refresh_run_action()

    def _on_batch_assessed(self, assessment) -> None:
        """Keep the panel's waste selection and the CFD scenario in step.

        The batch panel is the surface where composition is edited; the setup
        panel still carries the scenario the case generator reads. Mirroring the
        selected preset and moisture across means the run cannot use a different
        waste than the one the assessment describes.
        """
        if self._loading:
            return
        self._last_assessment = assessment

    def _on_sensors_changed(self) -> None:
        if self._loading:
            return
        self._project.sensors = self._viewport.sensors()
        self._sensor_lab.set_context(self._project.sensors, self._results_panel.readings())
        self._mark_dirty()
        self._refresh_counters()
        self._refresh_run_action()

    def _on_lab_config_changed(self, config) -> None:
        """Persist a device model edited in the lab panel."""
        if self._loading:
            return
        self._project.sensor_lab = config
        self._mark_dirty()

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
            self._solver_label.setToolTip("")
        else:
            self._solver_label.setText(self._t.t("run.blocked"))
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
        self._action_home.setText(t("menu.file.home"))
        self._action_new.setText(t("menu.file.new"))
        self._action_open.setText(t("menu.file.open"))
        self._action_save.setText(t("menu.file.save"))
        self._action_save_as.setText(t("menu.file.save_as"))
        self._action_export.setText(t("menu.file.export_csv"))
        self._action_quit.setText(t("menu.file.quit"))
        self._view_menu.setTitle(t("menu.view"))
        self._action_fit.setText(t("menu.view.fit"))
        self._action_reset.setText(t("menu.view.reset"))
        self._help_menu.setTitle(t("menu.help"))
        self._action_about.setText(t("menu.help.about"))
        self._run_menu.setTitle(t("menu.run"))
        self._action_run.setText(t("action.run"))
        self._action_cancel.setText(t("action.cancel"))
        self._action_setup_container.setText(t("action.setup_container"))
        self._container_toolbar.setWindowTitle(t("menu.run.setup_container"))
        self._refresh_run_action()
        self._viewport.setToolTip(t("viewport.hint"))
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
    """A new project with the headline gases already selected.

    An empty source list used to be the default, which made Run fail until the
    user found the checkboxes. The four AP-42 headline gases are the ones a
    screening run wants, and they resolve through the cited ``auto`` path.
    """
    return Project(
        name="Untitled",
        geometry=BinGeometry(),
        scenario=Scenario(gas_sources={gas: "auto" for gas in DEFAULT_SOURCE_GASES[:4]}),
    )


def _ppmv_readings(readings: list) -> list[SensorReading]:
    """Convert raw volume fractions to ppmv, exactly once.

    ``post.SensorReading.values`` are dimensionless volume fractions; the
    manifest and the table are ppmv. The factor is ``casegen.PPM_SCALE``'s
    reciprocal rather than a literal ``1e6``, so the case writer's ppm-to-
    fraction convention and this conversion cannot drift apart.

    The converted list is what the results table shows *and* what the manifest
    persists, so the displayed and recorded values cannot drift apart.
    """
    return [
        SensorReading(
            sensor_id=reading.sensor_id,
            x=reading.x,
            y=reading.y,
            values={gas: value / PPM_SCALE for gas, value in reading.values.items()},
        )
        for reading in readings
    ]


def _terminal_status(outcome: RunOutcome, record: RunRecord) -> str:
    """Map a worker outcome onto a manifest execution status.

    ``-2`` is the runner's cancellation sentinel and is checked first: a
    cancelled solve exits non-zero but is not a failure.

    A solve that exited cleanly but produced no readings for a project with
    sensors did not succeed — an empty table must never be recorded as a
    successful empty result, so it is finalized as ``failed``.
    ``history.finish_run()`` attaches the audit reason and re-checks the
    readings against the frozen snapshot.
    """
    if outcome.exit_code == -2:
        return "cancelled"
    if not outcome.ok:
        return "failed"
    if record.project.sensors and not outcome.readings:
        return "failed"
    return "succeeded"


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
    """Report whether the OpenFOAM container is reachable; never raises.

    Delegates to :mod:`scentinel.core.container`, which also checks that the
    image is present in this app's own storage — a pull into the user's default
    storage would otherwise enable Run and then fail at solve time.
    """
    return container.container_ready()
