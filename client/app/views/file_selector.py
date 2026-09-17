from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class FileSelector(QGroupBox):

    def __init__(self, parent=None):
        super().__init__("Arquivo", parent)
        self.selected_file_path = ""

        layout = QVBoxLayout(self)
        selection_layout = QHBoxLayout()

        self.file_label = QLabel("Nenhum arquivo selecionado")
        self.file_label.setWordWrap(True)
        selection_layout.addWidget(self.file_label, 1)

        select_button = QPushButton("Selecionar áudio")
        select_button.clicked.connect(self.select_audio)
        selection_layout.addWidget(select_button)
        layout.addLayout(selection_layout)

        info_layout = QHBoxLayout()
        info_layout.setSpacing(4)
        self.format_value = QLabel("-")
        self.size_value = QLabel("-")
        self.duration_value = QLabel("-")
        info_layout.addWidget(QLabel("Formato:"))
        info_layout.addWidget(self.format_value)
        info_layout.addWidget(QLabel("Tamanho:"))
        info_layout.addWidget(self.size_value)
        info_layout.addWidget(QLabel("Duração:"))
        info_layout.addWidget(self.duration_value)
        layout.addLayout(info_layout)

    def select_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo de áudio",
            "",
            "Arquivos de áudio (*.mp3 *.wav *.ogg *.flac *.m4a)",
        )

        if file_path:
            file_info = QFileInfo(file_path)
            self.selected_file_path = file_path
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
