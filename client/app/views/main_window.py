from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
)
from PySide6.QtCore import QFileInfo


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Processador de Áudio")
        self.resize(720, 480)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        title = QLabel("PROCESSADOR DE ÁUDIO")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        file_group = QGroupBox("Arquivo")
        file_layout = QVBoxLayout(file_group)

        selection_layout = QHBoxLayout()

        self.file_label = QLabel("Nenhum arquivo selecionado")
        self.file_label.setWordWrap(True)
        selection_layout.addWidget(self.file_label, 1)

        select_button = QPushButton("Selecionar áudio")
        select_button.clicked.connect(self.select_audio)
        selection_layout.addWidget(select_button)
        file_layout.addLayout(selection_layout)

        info_layout = QFormLayout()
        self.format_value = QLabel("-")
        self.size_value = QLabel("-")
        self.duration_value = QLabel("-")

        info_layout.addRow("Formato:", self.format_value)
        info_layout.addRow("Tamanho:", self.size_value)
        info_layout.addRow("Duração:", self.duration_value)

        file_layout.addLayout(info_layout)

        layout.addWidget(file_group)
        layout.addStretch()

    def select_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo de áudio",
            "",
            "Arquivos de áudio (*.mp3 *.wav *.ogg *.flac *.m4a)",
        )

        if file_path:
            file_info = QFileInfo(file_path)
            self.file_label.setText(file_path)
            self.format_value.setText(file_info.suffix().upper() or "-")
            self.size_value.setText(self.format_file_size(file_info.size()))

    @staticmethod
    def format_file_size(size_in_bytes):
        if size_in_bytes < 1024:
            return f"{size_in_bytes} B"
        if size_in_bytes < 1024 * 1024:
            return f"{size_in_bytes / 1024:.1f} KB"
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"