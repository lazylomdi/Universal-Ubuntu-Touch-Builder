"""Lightweight PySide6 desktop UI for romforge (Windows and Ubuntu)."""
from __future__ import annotations

import os
import json
import urllib.parse
import urllib.request
import shutil
import subprocess
import sys
from pathlib import Path

from desktop_ui.readiness_summary import summarize_readiness_report

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QSplitter, QTextBrowser,
    QWidget, QFileDialog, QCheckBox, QGroupBox, QDialog, QTabWidget, QDialogButtonBox,
)

ROOT = Path(__file__).resolve().parents[1]
ROMFORGE = ROOT / "romforge.py"


def adb_help(message: str) -> str:
    """Turn common ADB failures into beginner-friendly next steps."""
    lowered = message.lower()
    if "not found" in lowered or "no such file" in lowered:
        return "Next steps: install Android SDK Platform-Tools, ensure adb is on PATH, restart AndroidBuilder, then refresh devices."
    if "unauthorized" in lowered or "authoriz" in lowered:
        return "Next steps: unlock the phone, accept the USB debugging prompt, tick “Always allow” only if this is your trusted computer, then refresh devices."
    if "offline" in lowered:
        return "Next steps: reconnect the USB cable, try another data-capable cable or USB port, keep the phone unlocked, then refresh devices."
    if "timed out" in lowered or "timeout" in lowered:
        return "Next steps: reconnect the phone, keep it awake and unlocked, then retry. If it persists, restart the ADB server manually and refresh."
    if "multiple" in lowered:
        return "Next steps: select the exact phone by model and serial number. AndroidBuilder will not guess which device you intended."
    if "permission" in lowered or "access is denied" in lowered:
        return "Next steps: check USB debugging authorization and operating-system USB permissions. Do not run the app as administrator/root unless your platform setup specifically requires it."
    return "Next steps: check the USB data cable and port, keep the phone unlocked, confirm USB debugging is enabled and authorized, then refresh. Technical error details are shown above."


def make_button(text: str, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        button.setObjectName("primaryButton")
    return button


class DesktopWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AndroidBuilder")
        self.resize(1180, 780)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.build_running = False
        self.device_report_path: Path | None = None
        self.active_task = ""
        self.guided_inspection = False
        self.last_device_report = ""

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        brand = QLabel("AndroidBuilder")
        brand.setObjectName("brand")
        side.addWidget(brand)
        subtitle = QLabel("ROM WORKSPACE")
        subtitle.setObjectName("eyebrow")
        side.addWidget(subtitle)
        self.nav = QListWidget()
        self.nav.addItems(["Dashboard", "Check my phone", "Build wizard", "Build monitor", "Device manager"])
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.change_page)
        side.addWidget(self.nav, 1)
        device_status = QFrame()
        device_status.setObjectName("sidebarDevice")
        device_status_layout = QVBoxLayout(device_status)
        device_status_layout.setContentsMargins(10, 10, 10, 10)
        device_heading = QLabel("CONNECTED DEVICE")
        device_heading.setObjectName("eyebrow")
        self.sidebar_device_name = QLabel("No device detected")
        self.sidebar_device_name.setObjectName("sidebarDeviceName")
        self.sidebar_device_info = QLabel("ADB · waiting for scan")
        self.sidebar_device_info.setObjectName("muted")
        self.sidebar_device_info.setWordWrap(True)
        device_status_layout.addWidget(device_heading)
        device_status_layout.addWidget(self.sidebar_device_name)
        device_status_layout.addWidget(self.sidebar_device_info)
        side.addWidget(device_status)
        side_note = QLabel("Python engine · Windows 10 / Ubuntu")
        side_note.setObjectName("muted")
        side.addWidget(side_note)
        layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(16)
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Your connected Android devices.")
        self.page_subtitle.setObjectName("muted")
        header_row = QHBoxLayout()
        header_row.addWidget(self.page_title, 1)
        self.home_button = make_button("⌂ Home")
        self.home_button.clicked.connect(self.go_home)
        self.home_button.setVisible(False)
        header_row.addWidget(self.home_button)
        self.help_button = make_button("? Help")
        self.help_button.clicked.connect(self.show_help)
        header_row.addWidget(self.help_button)
        content_layout.addLayout(header_row)
        content_layout.addWidget(self.page_subtitle)
        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages, 1)
        layout.addWidget(content, 1)

        self.dashboard = self.make_dashboard()
        self.phone_check = self.make_phone_check()
        self.wizard = self.make_wizard()
        self.monitor = self.make_monitor()
        self.devices = self.make_devices()
        self.device_detail = self.make_device_detail()
        for page in (self.dashboard, self.phone_check, self.wizard, self.monitor, self.devices, self.device_detail):
            self.pages.addWidget(page)

        self.apply_styles()
        self.refresh_devices()

    def change_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        titles = [
            ("Dashboard", "Your build environment at a glance."),
            ("Check my phone", "A guided, read-only check of a connected Android phone."),
            ("Build wizard", "Configure a ROM build before launching it."),
            ("Build monitor", "Live output from the active or most recent task."),
            ("Device manager", "Advanced device selection and technical inspection details."),
        ]
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])
        self.home_button.setVisible(False)

    def card(self, title: str, value: str, detail: str = "") -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        box = QVBoxLayout(frame)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        metric = QLabel(value)
        metric.setObjectName("metric")
        note = QLabel(detail)
        note.setObjectName("muted")
        note.setWordWrap(True)
        box.addWidget(heading)
        box.addWidget(metric)
        box.addWidget(note)
        return frame

    def make_dashboard(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setSpacing(16)
        self.dashboard_hint = QLabel("Phones connected through Android Debug Bridge appear here.")
        self.dashboard_hint.setObjectName("muted")
        box.addWidget(self.dashboard_hint)
        self.device_cards_widget = QWidget()
        self.device_cards_layout = QHBoxLayout(self.device_cards_widget)
        self.device_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.device_cards_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        box.addWidget(self.device_cards_widget)
        self.dashboard_refresh_button = make_button("Refresh devices", True)
        self.dashboard_refresh_button.clicked.connect(self.refresh_devices)
        box.addWidget(self.dashboard_refresh_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addStretch()
        return page

    def render_dashboard_devices(self, devices: list[dict[str, str]]) -> None:
        while self.device_cards_layout.count():
            item = self.device_cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not devices:
            empty = QLabel("No device connected")
            empty.setObjectName("muted")
            empty.setMinimumHeight(130)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_cards_layout.addWidget(empty)
            self.dashboard_hint.setText("Connect a phone with USB debugging enabled, then refresh.")
            return
        self.dashboard_hint.setText(f"{len(devices)} connected device(s) · Select a phone to inspect it.")
        for device in devices:
            button = QPushButton()
            button.setObjectName("deviceTile")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumSize(150, 155)
            button.setMaximumWidth(210)
            tile = QVBoxLayout(button)
            icon = QLabel("📱")
            icon.setObjectName("phoneIcon")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel(device["name"])
            name.setObjectName("deviceTileName")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setWordWrap(True)
            state = QLabel(device["state"])
            state.setObjectName("muted")
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Keep the icon, model name, and state visually grouped inside one tile.
            tile.setContentsMargins(8, 8, 8, 8)
            tile.setSpacing(2)
            for child in (icon, name, state):
                child.setStyleSheet("background: transparent; border: none; padding: 0;")
            icon.setMinimumHeight(72)
            name.setMinimumHeight(22)
            state.setMinimumHeight(20)
            tile.addWidget(icon, 1)
            tile.addWidget(name)
            tile.addWidget(state)
            button.clicked.connect(lambda checked=False, serial=device["serial"]: self.open_device_detail(serial))
            self.device_cards_layout.addWidget(button)

    def make_device_detail(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        self.detail_device_name = QLabel("Select a connected phone")
        self.detail_device_name.setObjectName("sectionTitle")
        self.detail_device_serial = QLabel("")
        self.detail_device_serial.setObjectName("muted")
        box.addWidget(self.detail_device_name)
        box.addWidget(self.detail_device_serial)
        self.detail_device_summary = QLabel("Select a phone on the dashboard to inspect its reported details.")
        self.detail_device_summary.setObjectName("notice")
        self.detail_device_summary.setWordWrap(True)
        box.addWidget(self.detail_device_summary)
        self.detail_device_status = QLabel("Technical report")
        self.detail_device_status.setObjectName("sectionTitle")
        box.addWidget(self.detail_device_status)
        self.detail_device_report = QTextBrowser()
        self.detail_device_report.setObjectName("deviceReport")
        self.detail_device_report.setOpenExternalLinks(False)
        self.detail_device_report.setPlaceholderText("The detailed device report will appear here after inspection.")
        box.addWidget(self.detail_device_report, 1)
        report_actions = QHBoxLayout()
        self.detail_copy_button = make_button("Copy report")
        self.detail_copy_button.clicked.connect(self.copy_detail_device_report)
        self.detail_export_button = make_button("Export report…")
        self.detail_export_button.clicked.connect(self.export_detail_device_report)
        report_actions.addWidget(self.detail_copy_button)
        report_actions.addWidget(self.detail_export_button)
        report_actions.addStretch()
        box.addLayout(report_actions)
        actions = QHBoxLayout()
        self.detail_inspect_button = make_button("Inspect / refresh details", True)
        self.detail_inspect_button.clicked.connect(self.inspect_dashboard_device)
        actions.addWidget(self.detail_inspect_button)
        actions.addStretch()
        box.addLayout(actions)
        return page

    def open_device_detail(self, serial: str) -> None:
        """Open a dedicated detail page for the explicitly selected dashboard device."""
        self.selected_dashboard_serial = serial
        item = next(
            (self.device_list.item(i) for i in range(self.device_list.count())
             if self.device_list.item(i).data(Qt.ItemDataRole.UserRole) == serial),
            None,
        )
        if item is None:
            self.detail_device_name.setText("Device no longer detected")
            self.detail_device_serial.setText(serial)
            self.detail_device_summary.setText("Refresh the dashboard and reconnect the phone before inspecting it.")
            self.detail_device_report.clear()
        else:
            name = item.data(Qt.ItemDataRole.UserRole + 2) or serial
            state = item.data(Qt.ItemDataRole.UserRole + 1) or "unknown"
            self.detail_device_name.setText(name)
            self.detail_device_serial.setText(f"Serial: {serial} · ADB state: {state}")
            self.detail_device_summary.setText("Device selected. Starting a read-only inspection to load its technical summary…")
            self.detail_device_report.setMarkdown(self.last_device_report if self.last_device_report else "")
        self.pages.setCurrentWidget(self.device_detail)
        self.page_title.setText("Device details")
        self.page_subtitle.setText("Technical summary and read-only inspection results for the selected phone.")
        self.home_button.setVisible(True)
        self.nav.clearSelection()
        # Tile clicks automatically start inspection without a second click.
        QTimer.singleShot(0, lambda: self.inspect_dashboard_device(auto=True))

    def inspect_dashboard_device(self, auto: bool = False) -> None:
        serial = getattr(self, "selected_dashboard_serial", "")
        item = next(
            (self.device_list.item(i) for i in range(self.device_list.count())
             if self.device_list.item(i).data(Qt.ItemDataRole.UserRole) == serial),
            None,
        )
        if item is None:
            QMessageBox.warning(self, "Device not connected", "Return home, refresh the device list, and select a connected phone.")
            return
        self.device_list.setCurrentItem(item)
        if item.data(Qt.ItemDataRole.UserRole + 1) != "device":
            QMessageBox.warning(self, "Device not ready", f"ADB reports state {item.data(Qt.ItemDataRole.UserRole + 1)!r}. Check the help instructions and refresh.")
            return
        self.guided_inspection = False
        self.inspect_device(skip_confirmation=auto)

    def go_home(self) -> None:
        self.home_button.setVisible(False)
        self.nav.setCurrentRow(0)
        self.pages.setCurrentWidget(self.dashboard)
        self.page_title.setText("Dashboard")
        self.page_subtitle.setText("Your connected Android devices.")
        self.refresh_devices()

    def show_help(self) -> None:
        """Open structured help with phone setup steps and dependency status."""
        dialog = QDialog(self)
        dialog.setWindowTitle("AndroidBuilder Help")
        dialog.resize(640, 500)
        outer = QVBoxLayout(dialog)
        tabs = QTabWidget()
        outer.addWidget(tabs, 1)

        connect_page = QWidget()
        connect_layout = QVBoxLayout(connect_page)
        intro = QLabel("Connect your Android phone")
        intro.setObjectName("sectionTitle")
        connect_layout.addWidget(intro)
        steps = QLabel(
            "1. Use a USB cable that supports data transfer.\n\n"
            "2. Unlock your phone. In Settings, enable Developer options "
            "and then USB debugging. The menu names vary by manufacturer.\n\n"
            "3. Connect the phone to this computer. When prompted on the phone, "
            "review the computer's RSA fingerprint and accept only if you trust this computer.\n\n"
            "4. Click Home, then Refresh devices. Your phone should appear as a tile.\n\n"
            "5. Select the phone tile and click Inspect / refresh details to run a read-only check."
        )
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.TextFormat.PlainText)
        connect_layout.addWidget(steps)
        cable_note = QLabel(
            "If the phone does not appear: try another data cable or USB port, keep the phone unlocked, "
            "recheck the authorization prompt, and refresh again."
        )
        cable_note.setObjectName("notice")
        cable_note.setWordWrap(True)
        connect_layout.addWidget(cable_note)
        connect_layout.addStretch()
        tabs.addTab(connect_page, "Connect a phone")

        deps_page = QWidget()
        deps_layout = QVBoxLayout(deps_page)
        deps_intro = QLabel("Dependency availability")
        deps_intro.setObjectName("sectionTitle")
        deps_layout.addWidget(deps_intro)
        deps_note = QLabel(
            "Available means the tool can be found from this running application. "
            "Optional tools are only needed for their corresponding build backend."
        )
        deps_note.setObjectName("muted")
        deps_note.setWordWrap(True)
        deps_layout.addWidget(deps_note)
        dependency_rows = [
            ("Python", bool(sys.executable), "Runs AndroidBuilder"),
            ("PySide6", self._module_available("PySide6"), "Desktop interface"),
            ("ROMForge CLI", ROMFORGE.is_file(), "Inspection and build commands"),
            ("ADB / Platform-Tools", bool(shutil.which("adb")), "Phone detection and inspection"),
            ("Git", bool(shutil.which("git")), "Source control and source checkout"),
            ("Java", bool(shutil.which("java")), "Android build prerequisite"),
            ("repo", bool(shutil.which("repo")), "Android source synchronization"),
            ("Docker (optional)", bool(shutil.which("docker")), "Docker build backend"),
            ("GitHub CLI (optional)", bool(shutil.which("gh")), "GitHub Actions workflow support"),
        ]
        for name, available, purpose in dependency_rows:
            row = QFrame()
            row.setObjectName("card")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 7, 10, 7)
            status = QLabel("✓ Found" if available else "✕ Missing")
            status.setMinimumWidth(85)
            status.setStyleSheet("color: #75cfc1;" if available else "color: #ff8b8b;")
            detail = QLabel(f"{name}\n{purpose}")
            detail.setWordWrap(True)
            row_layout.addWidget(status)
            row_layout.addWidget(detail, 1)
            deps_layout.addWidget(row)
        deps_layout.addStretch()
        tabs.addTab(deps_page, "Dependencies")

        note = QLabel(
            "This is an availability check, not an installer. It does not prove that a phone supports "
            "Ubuntu Touch or that a ROM build will succeed."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        outer.addWidget(buttons)
        dialog.exec()

    @staticmethod
    def _module_available(module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    def make_wizard(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        form_group = QGroupBox("Build configuration")
        form = QFormLayout(form_group)
        self.version = QComboBox()
        self.version.addItems(["14", "13", "12", "11", "10", "9", "8", "7", "6", "5", "4"])
        self.codename = QLineEdit()
        self.codename.setPlaceholderText("e.g. sunfish")
        self.vendor = QLineEdit()
        self.vendor.setPlaceholderText("Optional vendor hint")
        self.arch = QComboBox()
        self.arch.addItems(["arm64", "armv7", "x86_64", "x86"])
        self.source = QComboBox()
        self.source.addItems(["lineage", "aosp"])
        self.backend = QComboBox()
        self.backend.addItems(["local", "docker", "github-actions"])
        self.jobs = QSpinBox()
        self.jobs.setRange(1, max(1, os.cpu_count() or 4))
        self.jobs.setValue(min(4, max(1, os.cpu_count() or 4)))
        self.workdir = QLineEdit(str(ROOT / "romforge-src"))
        choose_dir = make_button("Browse…")
        choose_dir.clicked.connect(self.choose_workdir)
        work_row = QHBoxLayout()
        work_row.addWidget(self.workdir, 1)
        work_row.addWidget(choose_dir)
        work_widget = QWidget()
        work_widget.setLayout(work_row)
        self.lunch = QLineEdit()
        self.lunch.setPlaceholderText("Optional; e.g. lineage_sunfish-userdebug")
        self.device_tree = QLineEdit()
        self.vendor_tree = QLineEdit()
        self.kernel_tree = QLineEdit()
        self.recovery = QLineEdit()
        self.gapps = QCheckBox("Include Google apps (if supported by selected build)")
        self.root_option = QCheckBox("Include root customization")
        self.dry_run = QCheckBox("Dry run (do not run the build pipeline)")
        self.dry_run.setChecked(True)
        form.addRow("Android version", self.version)
        form.addRow("Device codename *", self.codename)
        form.addRow("Vendor hint", self.vendor)
        form.addRow("Architecture", self.arch)
        form.addRow("Source", self.source)
        form.addRow("Backend", self.backend)
        form.addRow("Parallel jobs", self.jobs)
        form.addRow("Work directory", work_widget)
        form.addRow("Lunch target", self.lunch)
        form.addRow("Device tree URL", self.device_tree)
        form.addRow("Vendor tree URL", self.vendor_tree)
        form.addRow("Kernel tree URL", self.kernel_tree)
        form.addRow("Recovery URL", self.recovery)
        form.addRow("", self.gapps)
        form.addRow("", self.root_option)
        form.addRow("", self.dry_run)
        outer.addWidget(form_group)
        note = QLabel("The first launch defaults to dry-run. Uncheck it only after reviewing the source, target, backend, and disk requirements.")
        note.setObjectName("notice")
        note.setWordWrap(True)
        outer.addWidget(note)
        actions = QHBoxLayout()
        actions.addStretch()
        start = make_button("Review & start build", True)
        start.clicked.connect(self.start_build)
        actions.addWidget(start)
        outer.addLayout(actions)
        outer.addStretch()
        return page

    def make_monitor(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        self.build_status = QLabel("No task started")
        self.build_status.setObjectName("statusPill")
        box.addWidget(self.build_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        box.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setPlaceholderText("Build output will appear here when a task starts.")
        box.addWidget(self.log, 1)
        actions = QHBoxLayout()
        clear = make_button("Clear log")
        clear.clicked.connect(self.log.clear)
        self.cancel_button = make_button("Terminate process")
        self.cancel_button.clicked.connect(self.cancel_process)
        self.cancel_button.setEnabled(False)
        actions.addWidget(clear)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        box.addLayout(actions)
        return page

    def open_device_check(self) -> None:
        """Open the guided phone-check workflow, not the advanced device manager."""
        self.nav.setCurrentRow(1)
        self.refresh_devices()

    def make_phone_check(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setSpacing(16)

        intro = QFrame()
        intro.setObjectName("heroCard")
        intro_layout = QVBoxLayout(intro)
        eyebrow = QLabel("DEVICE READINESS")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Let's check your phone.")
        title.setObjectName("heroTitle")
        description = QLabel(
            "This guided check reads information exposed by Android Debug Bridge (ADB). "
            "It does not unlock, root, reboot, erase, or flash your phone."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        intro_layout.addWidget(eyebrow)
        intro_layout.addWidget(title)
        intro_layout.addWidget(description)
        box.addWidget(intro)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_heading = QLabel("STEP 1 · CONNECT")
        status_heading.setObjectName("cardTitle")
        self.phone_check_status = QLabel("Checking for connected phones…")
        self.phone_check_status.setObjectName("sectionTitle")
        self.phone_check_status.setWordWrap(True)
        self.phone_check_detail = QLabel(
            "Use a USB data cable, enable USB debugging, unlock your phone, and accept the authorization prompt."
        )
        self.phone_check_detail.setObjectName("muted")
        self.phone_check_detail.setWordWrap(True)
        status_layout.addWidget(status_heading)
        status_layout.addWidget(self.phone_check_status)
        status_layout.addWidget(self.phone_check_detail)
        box.addWidget(status_card)

        steps = QFrame()
        steps.setObjectName("card")
        steps_layout = QVBoxLayout(steps)
        steps_title = QLabel("What happens next")
        steps_title.setObjectName("sectionTitle")
        steps_text = QLabel(
            "1. Scan for connected phones.\n"
            "2. Select the intended phone if more than one is connected.\n"
            "3. Run a read-only inspection and review the compatibility evidence.\n\n"
            "A detected phone is not proof that Ubuntu Touch supports it. Unknown means the evidence is incomplete."
        )
        steps_text.setObjectName("muted")
        steps_text.setWordWrap(True)
        steps_layout.addWidget(steps_title)
        steps_layout.addWidget(steps_text)
        box.addWidget(steps)

        actions = QHBoxLayout()
        scan = make_button("Scan for phones", True)
        scan.clicked.connect(self.refresh_devices)
        select = make_button("Choose phone and inspect")
        select.clicked.connect(self.continue_phone_check)
        actions.addWidget(scan)
        actions.addWidget(select)
        actions.addStretch()
        box.addLayout(actions)

        self.phone_technical_toggle = make_button("Show detailed technical report")
        self.phone_technical_toggle.setCheckable(True)
        self.phone_technical_toggle.toggled.connect(self.toggle_phone_technical_details)
        box.addWidget(self.phone_technical_toggle)
        self.phone_technical_report = QTextBrowser()
        self.phone_technical_report.setReadOnly(True)
        self.phone_technical_report.setOpenExternalLinks(False)
        self.phone_technical_report.setObjectName("deviceReport")
        self.phone_technical_report.setMinimumHeight(180)
        self.phone_technical_report.setVisible(False)
        box.addWidget(self.phone_technical_report, 1)
        box.addStretch()
        return page

    def toggle_phone_technical_details(self, expanded: bool) -> None:
        """Show or hide the full report directly on the guided phone-check page."""
        self.phone_technical_report.setVisible(expanded)
        self.phone_technical_toggle.setText(
            "Hide detailed technical report" if expanded else "Show detailed technical report"
        )
        if expanded and not self.last_device_report:
            self.phone_technical_report.setPlainText(
                "No inspection report is available yet. Scan for phones and run an inspection first."
            )

    def continue_phone_check(self) -> None:
        """Continue to inspection when exactly one authorized device is available."""
        selected = [
            self.device_list.item(index)
            for index in range(self.device_list.count())
            if self.device_list.item(index).data(Qt.ItemDataRole.UserRole)
        ]
        ready = [item for item in selected if item.data(Qt.ItemDataRole.UserRole + 1) == "device"]
        # Keep the beginner workflow active even when the user must select a
        # device in Device Manager first. Its Inspect button then returns here
        # with the result instead of silently switching to the advanced screen.
        self.guided_inspection = True
        if len(selected) == 1 and len(ready) == 1:
            self.device_list.setCurrentItem(ready[0])
            self.nav.setCurrentRow(4)
            self.inspect_device()
            return
        self.open_device_manager()
        if not selected:
            self.phone_check_status.setText("No phone available to inspect")
            self.phone_check_detail.setText("Scan again after connecting and authorizing a phone.")
        elif len(selected) > 1:
            self.phone_check_status.setText("Choose which phone to inspect")
            self.phone_check_detail.setText("Several devices are connected. Select the exact model and serial number in Device Manager.")
        else:
            self.phone_check_status.setText("Phone needs attention before inspection")
            self.phone_check_detail.setText("Resolve the ADB state shown in Device Manager, then scan again.")

    def open_device_manager(self) -> None:
        """Open advanced device selection and inspection."""
        self.nav.setCurrentRow(4)

    def make_devices(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.device_list = QListWidget()
        self.device_list.setMinimumWidth(190)
        self.device_list.setMaximumWidth(340)
        self.device_list.setMinimumHeight(240)
        self.device_list.setUniformItemSizes(True)
        self.device_count_label = QLabel("No devices scanned yet")
        self.device_count_label.setObjectName("muted")
        self.device_list.currentItemChanged.connect(self.update_selected_device_summary)
        splitter.addWidget(self.device_list)
        details = QFrame()
        details.setObjectName("card")
        detail_box = QVBoxLayout(details)
        title = QLabel("Device inspection")
        title.setObjectName("sectionTitle")
        detail_box.addWidget(title)
        detail_box.addWidget(self.device_count_label)
        guidance = QLabel(
            "Refresh lists ADB devices. Inspection is read-only; it will not unlock, root, reboot, erase, or flash your phone."
        )
        guidance.setObjectName("muted")
        guidance.setWordWrap(True)
        detail_box.addWidget(guidance)
        steps = QLabel(
            "<b>Getting started</b> · Connect with a USB data cable, enable USB debugging, "
            "unlock the phone and accept its authorization prompt. Then refresh devices and inspect the selected phone.<br><br>"
            "<b>Read results carefully:</b> detection does not mean Ubuntu Touch is supported. "
            "<i>Unknown</i> means evidence is missing. A locked bootloader does not by itself tell us whether unlocking is allowed."
        )
        steps.setObjectName("notice")
        steps.setWordWrap(True)
        steps.setMaximumHeight(76)
        detail_box.addWidget(steps)
        self.device_image = QLabel("No device image loaded")
        self.device_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_image.setMinimumHeight(100)
        self.device_image.setMaximumHeight(150)
        self.device_image.setMinimumWidth(0)
        self.device_image.setScaledContents(False)
        self.device_image_source = QLabel("Images are searched on Wikimedia Commons; license/source details are shown below.")
        self.device_image_source.setWordWrap(True)
        self.device_image_source.setOpenExternalLinks(True)
        image_actions = QHBoxLayout()
        find_image = make_button("Find device image")
        find_image.clicked.connect(self.find_device_image)
        save_image = make_button("Save image…")
        save_image.clicked.connect(self.save_device_image)
        image_actions.addWidget(find_image)
        image_actions.addWidget(save_image)
        image_actions.addStretch()
        self.device_image_data: bytes | None = None
        self.device_image_toggle = make_button("Show optional device image")
        self.device_image_toggle.setCheckable(True)
        self.device_image_toggle.toggled.connect(self.toggle_device_image_section)
        detail_box.addWidget(self.device_image_toggle)
        self.device_image_section = QWidget()
        image_section_layout = QVBoxLayout(self.device_image_section)
        image_section_layout.setContentsMargins(0, 0, 0, 0)
        image_heading = QLabel("Optional device image · Wikimedia Commons")
        image_heading.setObjectName("muted")
        image_section_layout.addWidget(image_heading)
        image_section_layout.addWidget(self.device_image)
        self.device_image_source.setMaximumHeight(38)
        image_section_layout.addWidget(self.device_image_source)
        image_section_layout.addLayout(image_actions)
        self.device_image_section.setVisible(False)
        detail_box.addWidget(self.device_image_section)
        self.device_summary = QLabel("No inspection results yet. Select an authorized phone and run the read-only check.")
        self.device_summary.setObjectName("notice")
        self.device_summary.setWordWrap(True)
        detail_box.addWidget(self.device_summary)
        self.device_output = QTextBrowser()
        self.device_output.setReadOnly(True)
        self.device_output.setOpenExternalLinks(False)
        self.device_output.setObjectName("deviceReport")
        self.device_output.setPlaceholderText("Inspect a selected phone to view its report.")
        self.device_output.setMinimumWidth(0)
        self.device_output.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Noto Sans", 11))
        self.device_output.setVisible(False)
        detail_box.addWidget(self.device_output, 2)
        self.technical_details_button = make_button("Show technical details")
        self.technical_details_button.setCheckable(True)
        self.technical_details_button.toggled.connect(self.toggle_technical_details)
        detail_box.addWidget(self.technical_details_button)
        self.report_actions_widget = QWidget()
        report_actions = QHBoxLayout(self.report_actions_widget)
        report_actions.setContentsMargins(0, 0, 0, 0)
        copy_report = make_button("Copy report")
        copy_report.clicked.connect(self.copy_device_report)
        export_report = make_button("Export report…")
        export_report.clicked.connect(self.export_device_report)
        report_actions.addWidget(copy_report)
        report_actions.addWidget(export_report)
        report_actions.addStretch()
        detail_box.addWidget(self.report_actions_widget)
        self.report_actions_widget.setVisible(False)
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760])
        box.addWidget(splitter, 1)
        actions = QHBoxLayout()
        refresh = make_button("Refresh devices", True)
        refresh.clicked.connect(self.refresh_devices)
        inspect = make_button("Inspect selected device")
        inspect.clicked.connect(self.inspect_device)
        inspect_fastboot = make_button("Inspect Fastboot mode")
        inspect_fastboot.clicked.connect(self.inspect_fastboot_device)
        actions.addWidget(refresh)
        actions.addWidget(inspect)
        actions.addWidget(inspect_fastboot)
        actions.addStretch()
        box.addLayout(actions)
        return page

    def copy_detail_device_report(self) -> None:
        report = self.last_device_report.strip()
        if not report:
            QMessageBox.information(self, "No report yet", "Wait for inspection to finish before copying the report.")
            return
        QApplication.clipboard().setText(report)
        QMessageBox.information(self, "Report copied", "The complete technical report has been copied.")

    def export_detail_device_report(self) -> None:
        report = self.last_device_report.strip()
        if not report:
            QMessageBox.information(self, "No report yet", "Wait for inspection to finish before exporting the report.")
            return
        serial = getattr(self, "selected_dashboard_serial", "device")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in serial)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export device report", f"androidbuilder-{safe_name}-report.md",
            "Markdown report (*.md);;Text file (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Could not save the report:\n{exc}")
            return
        QMessageBox.information(self, "Report exported", f"Report saved to:\n{path}")

    def copy_device_report(self) -> None:
        """Copy the complete rendered report as Markdown/plain text to the clipboard."""
        report = self.device_output.toMarkdown().strip()
        if not report:
            QMessageBox.information(self, "No report yet", "Inspect a connected device before copying its report.")
            return
        QApplication.clipboard().setText(report)
        self.build_status.setText("Device report copied")
        QMessageBox.information(self, "Report copied", "The inspection report has been copied to the clipboard.")

    def export_device_report(self) -> None:
        """Export the current report as a Markdown file."""
        report = self.device_output.toMarkdown().strip()
        if not report:
            QMessageBox.information(self, "No report yet", "Inspect a connected device before exporting its report.")
            return
        default_name = "androidbuilder-device-report.md"
        if self.device_report_path is not None:
            default_name = self.device_report_path.name
        path, _ = QFileDialog.getSaveFileName(
            self, "Export device report", default_name, "Markdown report (*.md);;Text file (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Could not save the report:\n{exc}")
            return
        QMessageBox.information(self, "Report exported", f"Report saved to:\n{path}")

    def run_command(self, args: list[str], task_name: str) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Task already running", "Wait for the current task to finish before starting another.")
            return
        self.active_task = task_name
        self.build_status.setText(f"Running: {task_name}")
        self.progress.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.log.appendPlainText(f"$ {sys.executable} " + " ".join(args))
        self.process.start(sys.executable, args)

    def start_build(self) -> None:
        codename = self.codename.text().strip()
        if not codename:
            QMessageBox.warning(self, "Device codename required", "Enter the target device codename before continuing.")
            return
        summary = (
            f"Android {self.version.currentText()} / {codename}\n"
            f"Source: {self.source.currentText()} · Backend: {self.backend.currentText()}\n"
            f"Work directory: {self.workdir.text().strip()}\n"
            f"Dry run: {'yes' if self.dry_run.isChecked() else 'NO — this may download sources and use substantial disk space'}"
        )
        answer = QMessageBox.question(
            self, "Review build configuration",
            summary + "\n\nStart this command?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        args = [
            str(ROMFORGE), "build", "--version", self.version.currentText(),
            "--codename", codename, "--arch", self.arch.currentText(),
            "--source", self.source.currentText(), "--backend", self.backend.currentText(),
            "--jobs", str(self.jobs.value()), "--workdir", self.workdir.text().strip() or "./romforge-src",
        ]
        optional = [
            ("--vendor", self.vendor.text().strip()),
            ("--lunch-target", self.lunch.text().strip()),
            ("--device-tree-url", self.device_tree.text().strip()),
            ("--vendor-tree-url", self.vendor_tree.text().strip()),
            ("--kernel-tree-url", self.kernel_tree.text().strip()),
            ("--recovery", self.recovery.text().strip()),
        ]
        for flag, value in optional:
            if value:
                args.extend([flag, value])
        if self.gapps.isChecked():
            args.append("--gapps")
        if self.root_option.isChecked():
            args.append("--root")
        if self.dry_run.isChecked():
            args.append("--dry-run")
        self.log.clear()
        self.nav.setCurrentRow(3)
        self.run_command(args, "ROM build")

    def sync_dashboard_devices(self) -> None:
        devices = []
        for index in range(self.device_list.count()):
            item = self.device_list.item(index)
            serial = item.data(Qt.ItemDataRole.UserRole)
            if not serial:
                continue
            devices.append({
                "serial": serial,
                "name": item.data(Qt.ItemDataRole.UserRole + 2) or serial,
                "state": item.data(Qt.ItemDataRole.UserRole + 1) or "unknown",
            })
        self.render_dashboard_devices(devices)

    def refresh_devices(self) -> None:
        self.device_list.clear()
        self.device_count_label.setText("Scanning connected devices…")
        adb = shutil.which("adb")
        if not adb:
            self.device_list.addItem("ADB not found on PATH")
            self.sidebar_device_name.setText("ADB unavailable")
            self.sidebar_device_info.setText("Install Android platform tools, then refresh.")
            self.device_output.setPlainText("ADB was not found on PATH.\\n\\n" + adb_help("ADB not found"))
            self.device_count_label.setText("ADB unavailable — install Android Platform-Tools")
            if hasattr(self, "phone_check_status"):
                self.phone_check_status.setText("ADB is not available")
                self.phone_check_detail.setText("Install Android SDK Platform-Tools, ensure adb is on PATH, and click Scan for phones again.")
            self.sync_dashboard_devices()
            return
        try:
            result = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.device_list.addItem("Could not query ADB")
            self.sidebar_device_name.setText("ADB error")
            self.sidebar_device_info.setText(str(exc))
            self.device_output.setPlainText(f"Could not query ADB devices:\n{exc}")
            self.device_count_label.setText("Device scan failed — see details")
            if hasattr(self, "phone_check_status"):
                self.phone_check_status.setText("Could not scan for phones")
                self.phone_check_detail.setText(f"{exc}. Check the cable/ADB setup, then retry.")
            self.sync_dashboard_devices()
            return
        device_items = []
        for raw in result.stdout.splitlines()[1:]:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            serial = parts[0]
            state = parts[1] if len(parts) > 1 else "unknown"
            model = ""
            manufacturer = ""
            if state == "device":
                try:
                    model_result = subprocess.run(
                        [adb, "-s", serial, "shell", "getprop", "ro.product.model"],
                        capture_output=True, text=True, timeout=4, check=False,
                    )
                    model = model_result.stdout.strip() if model_result.returncode == 0 else ""
                    maker_result = subprocess.run(
                        [adb, "-s", serial, "shell", "getprop", "ro.product.manufacturer"],
                        capture_output=True, text=True, timeout=4, check=False,
                    )
                    manufacturer = maker_result.stdout.strip() if maker_result.returncode == 0 else ""
                except (OSError, subprocess.TimeoutExpired):
                    pass
            display_name = " ".join(part for part in (manufacturer, model) if part).strip()
            if not display_name:
                display_name = serial
            self.device_list.addItem(f"{display_name}  ·  {serial}  ·  {state}")
            item = self.device_list.item(self.device_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, serial)
            item.setData(Qt.ItemDataRole.UserRole + 1, state)
            item.setData(Qt.ItemDataRole.UserRole + 2, display_name)
            device_items.append(item)
        if result.returncode != 0:
            self.device_count_label.setText("Device scan failed — see Build monitor")
            self.sidebar_device_name.setText("ADB error")
            self.sidebar_device_info.setText(result.stderr.strip() or "adb devices returned a non-zero exit code.")
            self.device_output.setPlainText(
                "ADB could not list devices. Check the platform-tools installation and ADB server, then refresh.\n\n"
                + (result.stderr.strip() or f"ADB exited with code {result.returncode}.")
            )
            if hasattr(self, "phone_check_status"):
                self.phone_check_status.setText("Could not scan for phones")
                self.phone_check_detail.setText(result.stderr.strip() or f"ADB exited with code {result.returncode}. Check ADB setup and retry.")
            self.sync_dashboard_devices()
            return
        if not device_items:
            self.device_list.addItem("No devices detected")
            self.sidebar_device_name.setText("No device detected")
            self.sidebar_device_info.setText("Check USB debugging, cable, and authorization.")
            self.device_output.setPlainText("No ADB devices found.\\n\\n" + adb_help("no devices detected"))
            self.device_count_label.setText("0 devices detected")
        else:
            ready_count = sum(1 for entry in device_items if entry.data(Qt.ItemDataRole.UserRole + 1) == "device")
            unauthorized_count = sum(1 for entry in device_items if entry.data(Qt.ItemDataRole.UserRole + 1) == "unauthorized")
            self.device_count_label.setText(f"{len(device_items)} device(s) detected · {ready_count} ready · {unauthorized_count} awaiting authorization.")
            # Never silently choose a phone when multiple devices are connected.
            if len(device_items) == 1:
                self.device_list.setCurrentItem(device_items[0])
            else:
                self.device_list.setCurrentRow(-1)
                self.sidebar_device_name.setText("Select a device")
                self.sidebar_device_info.setText(f"{len(device_items)} devices detected. Choose the intended phone before inspection.")
                self.device_output.setPlainText("Multiple devices detected. Select the phone you want to inspect; no device has been selected automatically.\\n\\n" + adb_help("multiple devices"))
        if hasattr(self, "phone_check_status"):
            if not adb:
                self.phone_check_status.setText("ADB is not available")
                self.phone_check_detail.setText("Install Android SDK Platform-Tools and ensure adb is on PATH, then scan again.")
            elif result.returncode != 0:
                self.phone_check_status.setText("Could not scan for phones")
                self.phone_check_detail.setText(result.stderr.strip() or "Check the ADB installation and try again.")
            elif not device_items:
                self.phone_check_status.setText("No phone detected yet")
                self.phone_check_detail.setText("Connect with a USB data cable, enable USB debugging, authorize this computer, then scan again.")
            elif len(device_items) == 1 and device_items[0].data(Qt.ItemDataRole.UserRole + 1) == "device":
                selected_name = device_items[0].data(Qt.ItemDataRole.UserRole + 2)
                self.phone_check_status.setText(f"Phone detected: {selected_name}")
                self.phone_check_detail.setText("ADB is authorized. Continue to run the read-only inspection and review evidence.")
            else:
                self.phone_check_status.setText(f"{len(device_items)} phones/devices found")
                self.phone_check_detail.setText("Choose the intended phone and confirm its ADB state before inspection.")
        if result.stderr.strip():
            self.device_output.append("ADB stderr:\n" + result.stderr.strip())
        self.sync_dashboard_devices()

    def update_selected_device_summary(self, current, previous=None) -> None:
        """Keep the summary tied to the currently selected device in multi-device setups."""
        if current is None:
            return
        serial = current.data(Qt.ItemDataRole.UserRole)
        state = current.data(Qt.ItemDataRole.UserRole + 1)
        display_name = current.data(Qt.ItemDataRole.UserRole + 2) or serial
        if not serial or state is None:
            return
        total = sum(
            1 for index in range(self.device_list.count())
            if self.device_list.item(index).data(Qt.ItemDataRole.UserRole)
        )
        self.sidebar_device_name.setText(display_name)
        self.sidebar_device_info.setText(f"Selected: {serial} · ADB: {state} · {total} device(s) detected")
        if state == "device":
            self.device_output.setPlainText(
                f"Selected device: {display_name}\nSerial: {serial}\n"
                f"ADB state: {state}\n\n"
                "Only this selected serial will be used for inspection. "
                "Choose another row to inspect a different device."
            )
        else:
            self.device_output.setPlainText(
                f"Selected device: {display_name}\nSerial: {serial}\nADB state: {state}\n\n"
                "This device is not ready for inspection. Resolve its ADB state, then refresh."
            )

    def find_device_image(self) -> None:
        """Find a reusable Wikimedia Commons image, trying broader model searches."""
        item = self.device_list.currentItem()
        display_name = item.data(Qt.ItemDataRole.UserRole + 2) if item else ""
        serial = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if not display_name:
            QMessageBox.information(self, "Select a device", "Select a connected device first.")
            return

        # Exact Android model names rarely appear in Commons filenames. Try progressively
        # broader searches, while keeping the result's license and source attribution.
        search_terms = [display_name]
        normalized = display_name.lower()
        if "sm-a042f" in normalized or "a04e" in normalized:
            search_terms.extend(["Samsung Galaxy A04e", "Samsung Galaxy A04", "Samsung smartphone"])
        elif "g2199" in normalized or "xperia r1" in normalized:
            search_terms.extend(["Sony Xperia R1", "Sony Xperia smartphone", "Sony smartphone"])
        else:
            search_terms.extend([display_name.split()[-1], "Android smartphone"])
        search_terms = list(dict.fromkeys(term.strip() for term in search_terms if term.strip()))

        self.device_image_data = None
        self.device_image.clear()
        self.device_image.setText("Searching Wikimedia Commons…")
        self.device_image_source.setText("Trying the device model and broader manufacturer searches…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            chosen = None
            for term in search_terms:
                query = urllib.parse.urlencode({
                    "action": "query", "format": "json", "generator": "search",
                    "gsrsearch": f"filetype:bitmap {term}", "gsrnamespace": "6",
                    "gsrlimit": "12", "prop": "imageinfo", "iiprop": "url|extmetadata",
                    "iiurlwidth": "900",
                })
                api_url = "https://commons.wikimedia.org/w/api.php?" + query
                request = urllib.request.Request(
                    api_url, headers={"User-Agent": "AndroidBuilder/1.0 (device image lookup)"}
                )
                with urllib.request.urlopen(request, timeout=12) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                pages = payload.get("query", {}).get("pages", {})
                for page in pages.values():
                    info = (page.get("imageinfo") or [{}])[0]
                    meta = info.get("extmetadata", {})
                    license_name = meta.get("LicenseShortName", {}).get("value", "")
                    if info.get("thumburl") and info.get("descriptionurl") and license_name:
                        chosen = (info, meta, page.get("title", "Wikimedia Commons image"), term)
                        break
                if chosen:
                    break

            if not chosen:
                self.device_image.setText("No licensed image found for this device.")
                search_url = "https://commons.wikimedia.org/wiki/Special:MediaSearch?type=image&search=" + urllib.parse.quote(display_name)
                gsmarena_url = (
                    "https://www.gsmarena.com/sony_xperia_r1_%28plus%29-8922.php"
                    if "g2199" in normalized or "xperia r1" in normalized
                    else "https://www.gsmarena.com/samsung_galaxy_a04e-11945.php"
                    if "a04e" in normalized or "sm-a042f" in normalized
                    else ""
                )
                fallback_links = f'<br><a href="{gsmarena_url}">View device photos on GSMArena</a>' if gsmarena_url else ""
                self.device_image_source.setText(
                    f'<a href="{search_url}">Search Wikimedia Commons manually</a>{fallback_links}<br>'
                    "No suitable reusable image was found automatically. You can still inspect the device without an image."
                )
                return

            info, meta, title, matched_term = chosen
            with urllib.request.urlopen(info["thumburl"], timeout=15) as response:
                image_data = response.read()
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_data):
                raise ValueError("The image format could not be decoded.")
            self.device_image_data = image_data
            self.device_image.setPixmap(pixmap.scaled(
                max(1, self.device_image.width()), max(1, self.device_image.height()),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            license_name = meta.get("LicenseShortName", {}).get("value", "License not listed")
            artist = meta.get("Artist", {}).get("value", "Author not listed")
            source_url = info["descriptionurl"]
            self.device_image_source.setText(
                f'<b>{title}</b><br>Matched search: {matched_term}<br>'
                f'License: {license_name}<br>Author: {artist}<br>'
                f'<a href="{source_url}">Source and attribution</a>'
            )
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            self.device_image.setText("Image lookup failed")
            search_url = "https://commons.wikimedia.org/wiki/Special:MediaSearch?type=image&search=" + urllib.parse.quote(display_name)
            gsmarena_url = (
                "https://www.gsmarena.com/sony_xperia_r1_%28plus%29-8922.php"
                if "g2199" in normalized or "xperia r1" in normalized
                else "https://www.gsmarena.com/samsung_galaxy_a04e-11945.php"
                if "a04e" in normalized or "sm-a042f" in normalized
                else ""
            )
            fallback_links = f'<br><a href="{gsmarena_url}">View device photos on GSMArena</a>' if gsmarena_url else ""
            self.device_image_source.setText(
                f"Could not retrieve an image: {exc}<br>"
                f'<a href="{search_url}">Open Commons search</a>{fallback_links}'
            )
        finally:
            QApplication.restoreOverrideCursor()

    def save_device_image(self) -> None:
        if not self.device_image_data:
            QMessageBox.information(self, "No image", "Find and load an image before saving.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save device image", "device-image.jpg",
                                               "Image files (*.jpg *.jpeg *.png *.webp)")
        if not path:
            return
        try:
            Path(path).write_bytes(self.device_image_data)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save image:\\n{exc}")
            return
        QMessageBox.information(self, "Image saved", f"Saved image to:\\n{path}")

    def inspect_device(self, skip_confirmation: bool = False) -> None:
        item = self.device_list.currentItem()
        if not item:
            QMessageBox.information(self, "Select a device", "Click Refresh devices first.")
            return
        serial = item.data(Qt.ItemDataRole.UserRole)
        state = item.data(Qt.ItemDataRole.UserRole + 1)
        if not serial or state is None:
            QMessageBox.warning(self, "No connected device", "Select a valid device row, not a status message.")
            return
        if state != "device":
            QMessageBox.warning(self, "Device not ready", f"ADB reports state {state!r}. Unlock the phone and authorize USB debugging, then refresh.")
            return
        if not skip_confirmation:
            answer = QMessageBox.question(
                self, "Read-only inspection",
                f"Inspect {serial} using the existing Ubuntu Touch readiness checker?\n\nThis is read-only and does not flash or change the phone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.device_output.clear()
        self.device_summary.setText(f"Inspection running for {item.data(Qt.ItemDataRole.UserRole + 2) or serial}. This is a read-only check.")
        report_dir = Path.home() / ".local" / "share" / "AndroidBuilder"
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot save report", f"Could not create the report directory:\n{exc}")
            return
        self.device_report_path = report_dir / "device-readiness-report.md"
        try:
            self.device_report_path.unlink(missing_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot prepare report", f"Could not clear the previous report:\n{exc}")
            return
        self.device_output.setPlainText(
            f"Inspecting {serial} with read-only ADB commands...\n"
            f"Saving report to: {self.device_report_path}\n"
            "Waiting for the inspection command to finish..."
        )
        if getattr(self, "selected_dashboard_serial", None) == serial:
            self.pages.setCurrentWidget(self.device_detail)
            self.home_button.setVisible(True)
        else:
            self.nav.setCurrentRow(4)
        self.run_command([str(ROMFORGE), "ut-check", "--inspect-device", "--serial", serial, "--markdown-out", str(self.device_report_path)], "Device inspection")

    def inspect_fastboot_device(self) -> None:
        """Run read-only Fastboot inspection without requiring ADB or a selected list item."""
        answer = QMessageBox.question(
            self, "Read-only Fastboot inspection",
            "Put the phone in bootloader/Fastboot mode and connect it by USB first.\n\n"
            "This checks Fastboot variables and bootloader-reported state only. "
            "It does not reboot, unlock, erase, or flash the phone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        report_dir = Path.home() / ".local" / "share" / "AndroidBuilder"
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
            self.device_report_path = report_dir / "fastboot-readiness-report.md"
            self.device_report_path.unlink(missing_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot prepare report", f"Could not prepare the Fastboot report:\\n{exc}")
            return
        self.device_output.setPlainText(
            f"Inspecting Fastboot devices using read-only queries...\n"
            f"Saving report to: {self.device_report_path}\n"
            "No unlock or flash command will be issued."
        )
        self.nav.setCurrentRow(4)
        self.run_command(
            [str(ROMFORGE), "ut-check", "--inspect-fastboot", "--markdown-out", str(self.device_report_path)],
            "Fastboot inspection",
        )

    def choose_workdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select build work directory", self.workdir.text())
        if path:
            self.workdir.setText(path)

    def read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if data:
            self.log.appendPlainText(data.rstrip())
            self.device_output.append(data.rstrip())

    def read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError()).decode(errors="replace")
        if data:
            self.log.appendPlainText(data.rstrip())
            self.device_output.append(data.rstrip())

    def process_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self.progress.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.build_status.setText("Completed successfully" if code == 0 else f"Finished with exit code {code}")
        self.log.appendPlainText(f"\n[Process exited with code {code}]")
        self.device_output.append(f"[Process exited with code {code}]")
        task = self.active_task
        self.active_task = ""
        self.refresh_devices()
        # Refreshing devices updates the connection summary; for an inspection,
        # replace that summary with the completed report after the refresh.
        if task in {"Device inspection", "Fastboot inspection"}:
            if self.device_report_path is not None and self.device_report_path.is_file():
                try:
                    report = self.device_report_path.read_text(encoding="utf-8")
                    self.last_device_report = report
                    self.device_output.setMarkdown(report)
                    self.phone_technical_report.setMarkdown(report)
                    self.detail_device_report.setMarkdown(report)
                    summary = summarize_readiness_report(report, code)
                    self.device_summary.setText(summary)
                    self.detail_device_summary.setText(summary)
                    self.detail_device_status.setText("Inspection complete" if code == 0 else f"Inspection finished with exit code {code}")
                    self.log.appendPlainText(f"Readiness report loaded from {self.device_report_path}")
                    if self.guided_inspection:
                        self.phone_check_status.setText("Inspection complete" if code == 0 else "Inspection needs review")
                        self.phone_check_detail.setText(summary)
                        self.nav.setCurrentRow(1)
                except OSError as exc:
                    self.device_output.append(f"Could not read readiness report: {exc}")
                    if self.guided_inspection:
                        self.phone_check_status.setText("Could not load inspection report")
                        self.phone_check_detail.setText(f"{exc}. Open Device Manager for technical output.")
                        self.nav.setCurrentRow(1)
            else:
                error_summary = f"Inspection exited with code {code}, but no report was created. See Build monitor for stdout/stderr."
                self.device_output.append(error_summary)
                self.device_summary.setText(error_summary)
                if self.guided_inspection:
                    self.phone_check_status.setText("Inspection did not produce a report")
                    self.phone_check_detail.setText(error_summary)
                    self.nav.setCurrentRow(1)
            self.guided_inspection = False
    def toggle_device_image_section(self, expanded: bool) -> None:
        """Keep optional image search out of the main readiness-results view."""
        self.device_image_section.setVisible(expanded)
        self.device_image_toggle.setText(
            "Hide optional device image" if expanded else "Show optional device image"
        )

    def toggle_technical_details(self, expanded: bool) -> None:
        self.device_output.setVisible(expanded)
        self.report_actions_widget.setVisible(expanded)
        self.technical_details_button.setText("Hide technical details" if expanded else "Show technical details")

    def process_error(self, _error: QProcess.ProcessError) -> None:
        self.log.appendPlainText(f"Process error: {self.process.errorString()}")
        self.build_status.setText("Could not start process")
        self.progress.setVisible(False)
        self.cancel_button.setEnabled(False)

    def cancel_process(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            answer = QMessageBox.warning(
                self, "Terminate running process",
                "This sends a process termination request. Build cleanup may be incomplete. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.process.terminate()

    def apply_styles(self) -> None:
        # Inspired by the user's Android Toolkit reference: compact dark workspace,
        # strong sidebar navigation, quiet borders, and clear action emphasis.
        self.setStyleSheet("""
            QWidget { background: #101012; color: #e8e8ec; font-size: 12px; }
            QMainWindow { background: #101012; }
            #sidebar { background: #171719; border-right: 1px solid #29292d; }
            #brand { font-size: 18px; font-weight: 700; padding: 14px 8px 4px; color: #f5f5f7; }
            #eyebrow { color: #777780; font-size: 9px; font-weight: 700; letter-spacing: 1px; padding: 0 4px 8px; }
            #muted { color: #9999a2; }
            #pageTitle { font-size: 25px; font-weight: 700; color: #f1f1f4; }
            QListWidget { background: transparent; border: 0; outline: 0; padding: 8px 4px; min-width: 0; }
            QListWidget::item { padding: 13px 12px; border-radius: 5px; margin: 2px 0; color: #a6a6af; }
            QListWidget::item:selected { background: #29292e; color: #ffffff; border-left: 2px solid #a855f7; font-weight: 600; }
            #card, QGroupBox { background: #1b1b1e; border: 1px solid #2b2b30; border-radius: 8px; }
            #card { padding: 8px; }
            #cardTitle { color: #85858f; font-size: 10px; font-weight: 700; letter-spacing: .5px; }
            #metric { color: #f0f0f3; font-size: 18px; font-weight: 700; }
            #sectionTitle { font-size: 15px; font-weight: 700; color: #eeeeF2; }
            #notice { background: #111d1b; color: #75cfc1; border: 1px solid #203b36; border-radius: 6px; padding: 12px; }
            #sidebarDevice { background: #131315; border: 1px solid #2a2a2e; border-radius: 6px; }
            #sidebarDeviceName { color: #ededf0; font-weight: 700; }
            QGroupBox { margin-top: 10px; padding: 16px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #b5b5bf; }
            QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: #141416; color: #ededf0; border: 1px solid #333339; border-radius: 6px; padding: 8px; selection-background-color: #6336a6; }
            QComboBox QAbstractItemView { background: #202024; color: #ededf0; selection-background-color: #6336a6; }
            QCheckBox { spacing: 8px; color: #d6d6dc; }
            QPlainTextEdit { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 12px; }
            QTextBrowser#deviceReport { background: #18181c; color: #f0f0f4; border: 1px solid #3a3a43; border-radius: 6px; padding: 14px; font-size: 14px; selection-background-color: #6336a6; }
            QTextBrowser#deviceReport { min-width: 0; }
            QTextBrowser#deviceReport table { width: 100%; }
            QTextBrowser#deviceReport td, QTextBrowser#deviceReport th { padding: 6px 8px; }
            QTextBrowser#deviceReport pre { white-space: pre-wrap; }
            QTextBrowser#deviceReport p { margin-top: 5px; margin-bottom: 8px; line-height: 1.35; }\n            QTextBrowser#deviceReport li { margin-bottom: 4px; }
            QTextBrowser#deviceReport h1, QTextBrowser#deviceReport h2 { color: #f0f0f4; }
            QTextBrowser#deviceReport a { color: #75cfc1; }
            QPushButton { background: #202023; color: #dedee4; border: 1px solid #34343a; border-radius: 6px; padding: 9px 15px; font-weight: 600; }
            QPushButton:hover { background: #2a2a30; border-color: #4b4b55; }
            QPushButton#primaryButton { background: #6550a8; color: white; border-color: #8068ce; }
            QPushButton#primaryButton:hover { background: #7962bf; }
            QPushButton#deviceTile { background: #1b1b21; border: 1px solid #34343e; border-radius: 10px; padding: 14px; }
            QPushButton#deviceTile:hover { background: #29292f; border-color: #8068ce; }
            #phoneIcon { font-size: 44px; padding: 0; background: transparent; border: none; }
            #deviceTileName { font-size: 13px; font-weight: 700; color: #f0f0f4; background: transparent; border: none; padding: 0; }
            QPushButton#deviceTile QLabel { background: transparent; border: none; padding: 0; }
            #heroCard { background: #1b1b21; border: 1px solid #34343e; border-radius: 10px; }\n            #heroTitle { color: #f5f3ff; font-size: 26px; font-weight: 700; padding-top: 4px; padding-bottom: 4px; }\n            #statusPill { background: #142b27; color: #75cfc1; border: 1px solid #244a43; border-radius: 6px; padding: 9px; font-weight: 600; }
            QProgressBar { border: 0; background: #29292e; border-radius: 4px; height: 8px; text-align: center; }
            QProgressBar::chunk { background: #58b9a9; border-radius: 4px; }
            QScrollBar:vertical { background: #151517; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #3b3b42; min-height: 24px; border-radius: 4px; }
        """)

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AndroidBuilder")
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Noto Sans", 10))
    window = DesktopWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
