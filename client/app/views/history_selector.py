from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.audio_api import AudioApi


class HistorySection(QGroupBox):

    HEADERS = ("Data", "Arquivo", "Processamento", "Duração", "Status")
    PROCESSING_LABELS = {
        "volume": "Normalização de volume",
        "mono": "Conversão para mono",
        "speed": "Alteração da velocidade",
        "bitrate": "Redução da taxa de bits",
        "format": "Conversão de formato",
        "original": "Sem processamento",
    }

    def __init__(self, parent=None):
        super().__init__("Histórico", parent)

        self.api = AudioApi(parent=self)
        self.api.history_loaded.connect(self.set_history)
        self.api.request_failed.connect(self.show_request_error)

        refresh_button = QPushButton("Atualizar histórico")
        refresh_button.clicked.connect(self.api.fetch_history)
        self.status_label = QLabel("Carregando histórico...")
        actions_layout = QHBoxLayout()
        actions_layout.addWidget(self.status_label)
        actions_layout.addStretch()
        actions_layout.addWidget(refresh_button)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout = QVBoxLayout(self)
        layout.addLayout(actions_layout)
        layout.addWidget(self.table)

        self.api.fetch_history()

    def set_history(self, records):
        self.table.setRowCount(0)
        for record in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                self.format_date(record.get("created_at")),
                record.get("original_name", "-"),
                self.PROCESSING_LABELS.get(
                    record.get("processing_type"),
                    record.get("processing_type", "-"),
                ),
                self.format_duration(record.get("duration_sec")),
                self.format_status(record),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.status_label.setText(f"{len(records)} registro(s)")

    def show_request_error(self, message):
        self.status_label.setText(f"Erro ao carregar histórico: {message}")

    @staticmethod
    def format_date(value):
        if not value:
            return "-"
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        return str(value)[:10]

    @staticmethod
    def format_duration(duration_seconds):
        if duration_seconds is None:
            return "-"
        total_seconds = max(0, int(float(duration_seconds)))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def format_status(record):
        return "Excluído" if record.get("is_deleted") else "Concluído"
