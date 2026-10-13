"""
BrainLink Lite Monitor
----------------------
Live EEG waveform, headset metrics and CSV recording.

Run from the project root:
    python -m brainlink.gui
"""

import csv
import queue
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .parser import BrainLinkDataParser
from .serial_connection import BrainLinkSerial


class BrainLinkWindow(QMainWindow):
    """Main live-monitor window."""

    DISPLAY_SECONDS = 5
    MAX_POINTS = 12000
    MAX_QUEUE_BATCH = 20000

    PLOT_FIELDS = (
        ("Raw EEG", "raw", "Raw EEG (parser units)", "#35d0ba"),
        ("Signal", "signal", "Signal quality", "#f2a65a"),
        ("Attention", "attention", "Attention score", "#73b7ff"),
        ("Meditation", "meditation", "Meditation score", "#c792ea"),
        ("Delta", "delta", "Delta power", "#f07178"),
        ("Theta", "theta", "Theta power", "#c3e88d"),
    )

    def __init__(self):
        super().__init__()

        self.setWindowTitle("BrainLink Lite Monitor")
        self.resize(1400, 1000)

        self.data_queue = queue.Queue()
        self.connection = None
        self.parser = None
        self.csv_file = None
        self.csv_writer = None
        self.recording = False

        self.start_time = time.monotonic()
        self.sample_times = []
        self.plot_values = {field: [] for _, field, _, _ in self.PLOT_FIELDS}
        self.plot_widgets = {}
        self.plot_curves = {}

        self._build_ui()
        self._refresh_ports()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_display)
        self.timer.start(30)

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        # Connection controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Bluetooth COM port:"))

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        controls.addWidget(self.port_combo)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_ports)
        controls.addWidget(refresh)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._connect)
        controls.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect)
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.disconnect_button)

        controls.addStretch()
        layout.addLayout(controls)

        self.status_label = QLabel("Disconnected")
        layout.addWidget(self.status_label)

        # Six plots arranged in two columns. Independent axes keep
        # small scores readable alongside the much larger band powers.
        plots_grid = QGridLayout()
        plots_grid.setContentsMargins(0, 0, 0, 0)
        plots_grid.setHorizontalSpacing(8)
        plots_grid.setVerticalSpacing(8)

        for index, (title, field, y_label, color) in enumerate(self.PLOT_FIELDS):
            plot = pg.PlotWidget()
            plot.setBackground("#10151c")
            plot.setTitle(title, color="#ffffff", size="12pt")
            plot.setLabel("left", y_label)
            plot.setLabel("bottom", "Time", units="s")
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setXRange(-self.DISPLAY_SECONDS, 0, padding=0)
            plot.setMinimumHeight(190)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=True)

            curve = plot.plot(pen=pg.mkPen(color, width=1.5))
            self.plot_widgets[field] = plot
            self.plot_curves[field] = curve

            row, col = divmod(index, 2)
            plots_grid.addWidget(plot, row, col)

        plots_container = QWidget()
        plots_container.setLayout(plots_grid)
        layout.addWidget(plots_container, stretch=1)

        # Metric values retained from the original GUI.
        metrics = QGridLayout()
        self.metric_labels = {}

        fields = [
            ("Signal", "signal"),
            ("Attention", "attention"),
            ("Meditation", "meditation"),
            ("Delta", "delta"),
            ("Theta", "theta"),
            ("Low Alpha", "low_alpha"),
            ("High Alpha", "high_alpha"),
            ("Low Beta", "low_beta"),
            ("High Beta", "high_beta"),
            ("Low Gamma", "low_gamma"),
            ("High Gamma", "high_gamma"),
            ("Battery", "battery"),
            ("Heart", "heart"),
            ("Temperature", "temperature"),
        ]

        for index, (caption, field) in enumerate(fields):
            row = index // 7
            col = (index % 7) * 2
            metrics.addWidget(QLabel(caption + ":"), row, col)

            value = QLabel("--")
            value.setMinimumWidth(65)
            value.setStyleSheet("font-size: 13px; font-weight: bold;")
            metrics.addWidget(value, row, col + 1)
            self.metric_labels[field] = value

        layout.addLayout(metrics)

        # Recording controls
        record_controls = QHBoxLayout()

        self.record_button = QPushButton("Start Recording")
        self.record_button.clicked.connect(self._start_recording)
        record_controls.addWidget(self.record_button)

        self.stop_record_button = QPushButton("Stop Recording")
        self.stop_record_button.clicked.connect(self._stop_recording)
        self.stop_record_button.setEnabled(False)
        record_controls.addWidget(self.stop_record_button)

        clear_button = QPushButton("Clear Graph")
        clear_button.clicked.connect(self._clear_graph)
        record_controls.addWidget(clear_button)

        record_controls.addStretch()
        layout.addLayout(record_controls)

        self.setCentralWidget(root)

    def _refresh_ports(self):
        selected = self.port_combo.currentData()
        self.port_combo.clear()

        try:
            ports = BrainLinkSerial.list_ports()
        except Exception as error:
            QMessageBox.warning(self, "COM ports", str(error))
            return

        for port in ports:
            device = port["device"]
            description = port.get("description") or ""
            self.port_combo.addItem(f"{device} — {description}", device)

        if selected:
            index = self.port_combo.findData(selected)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def _connect(self):
        port = self.port_combo.currentData()

        if not port:
            QMessageBox.warning(self, "No COM port", "Select a COM port first.")
            return

        try:
            self.parser = BrainLinkDataParser(data_callback=self._receive_data)
            self.connection = BrainLinkSerial(data_callback=self.parser.parse)
            self.connection.connect(port)
        except Exception as error:
            self.connection = None
            self.parser = None
            QMessageBox.critical(self, "Connection failed", str(error))
            return

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.status_label.setText(f"Connected to {port}; waiting for data")

    def _receive_data(self, data):
        """Called from the serial reader thread.

        Snapshot the mutable parser data so queued samples don't all point
        to the same object as the parser updates it.
        """
        try:
            from dataclasses import replace
            snapshot = replace(data)
        except (TypeError, ValueError):
            snapshot = data
        self.data_queue.put(snapshot)

    def _disconnect(self):
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception as error:
                self.status_label.setText(f"Disconnect warning: {error}")

        self.connection = None
        self.parser = None

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_combo.setEnabled(True)
        if "warning" not in self.status_label.text().lower():
            self.status_label.setText("Disconnected")

    def _update_display(self):
        latest = None
        processed = 0

        # Process queued samples without blocking the GUI indefinitely.
        while processed < self.MAX_QUEUE_BATCH:
            try:
                data = self.data_queue.get_nowait()
            except queue.Empty:
                break

            latest = data
            processed += 1

            # Each parsed update is plotted against elapsed monotonic time.
            elapsed = time.monotonic() - self.start_time
            self.sample_times.append(elapsed)

            for _, field, _, _ in self.PLOT_FIELDS:
                self.plot_values[field].append(getattr(data, field, None))

            if self.recording and self.csv_writer:
                self._write_csv_row(data)

        if self.sample_times:
            if len(self.sample_times) > self.MAX_POINTS:
                self.sample_times = self.sample_times[-self.MAX_POINTS:]
                for field in self.plot_values:
                    self.plot_values[field] = self.plot_values[field][-self.MAX_POINTS:]

            now = self.sample_times[-1]
            times = np.asarray(self.sample_times, dtype=float) - now
            visible = times >= -self.DISPLAY_SECONDS

            for _, field, _, _ in self.PLOT_FIELDS:
                values = np.asarray(
                    [np.nan if value is None else value
                     for value in self.plot_values[field]],
                    dtype=float,
                )
                self.plot_curves[field].setData(times[visible], values[visible])

            # Keep all plots aligned on the same scrolling time window.
            for plot in self.plot_widgets.values():
                plot.setXRange(-self.DISPLAY_SECONDS, 0, padding=0)

        if latest is not None:
            fields = [
                "signal", "attention", "meditation",
                "delta", "theta", "low_alpha", "high_alpha",
                "low_beta", "high_beta", "low_gamma", "high_gamma",
                "battery", "heart", "temperature",
            ]

            for field in fields:
                value = getattr(latest, field, None)
                self.metric_labels[field].setText(
                    "--" if value is None else str(value)
                )

            self.status_label.setText(
                f"Receiving data — {len(self.sample_times)} updates in plot history"
            )

    def _start_recording(self):
        output_dir = Path("recordings")
        output_dir.mkdir(exist_ok=True)

        default_name = datetime.now().strftime("brainlink_%Y%m%d_%H%M%S.csv")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save BrainLink recording",
            str(output_dir / default_name),
            "CSV files (*.csv)",
        )

        if not path:
            return

        try:
            self.csv_file = open(path, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([
                "timestamp", "raw", "signal", "attention", "meditation",
                "delta", "theta", "low_alpha", "high_alpha",
                "low_beta", "high_beta", "low_gamma", "high_gamma",
                "battery", "heart", "temperature",
            ])

            self.recording = True
            self.record_button.setEnabled(False)
            self.stop_record_button.setEnabled(True)
            self.status_label.setText(f"Recording to {path}")

        except OSError as error:
            QMessageBox.critical(self, "Recording failed", str(error))
            self._stop_recording()

    def _write_csv_row(self, data):
        fields = [
            "raw", "signal", "attention", "meditation",
            "delta", "theta", "low_alpha", "high_alpha",
            "low_beta", "high_beta", "low_gamma", "high_gamma",
            "battery", "heart", "temperature",
        ]
        self.csv_writer.writerow([
            datetime.now().isoformat(timespec="milliseconds"),
            *[getattr(data, field, None) for field in fields],
        ])

    def _stop_recording(self):
        self.recording = False

        if self.csv_file:
            try:
                self.csv_file.flush()
                self.csv_file.close()
            except OSError:
                pass

        self.csv_file = None
        self.csv_writer = None

        if hasattr(self, "record_button"):
            self.record_button.setEnabled(True)
            self.stop_record_button.setEnabled(False)

    def _clear_graph(self):
        self.sample_times.clear()
        for field in self.plot_values:
            self.plot_values[field].clear()
            self.plot_curves[field].clear()
        self.start_time = time.monotonic()

    def closeEvent(self, event):
        self._stop_recording()
        self._disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = BrainLinkWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
