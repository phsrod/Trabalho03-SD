from PySide6.QtCore import QFileInfo, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class FileSelector(QGroupBox):
    audio_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Arquivo", parent)
        self.selected_file_path = ""
        self.metadata_player = QMediaPlayer(self)
        self.metadata_audio_output = QAudioOutput(self)
        self.metadata_player.setAudioOutput(self.metadata_audio_output)
        self.metadata_player.durationChanged.connect(self.update_duration)

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
        """Abre um diálogo para selecionar um arquivo de áudio e atualiza as informações do arquivo selecionado."""
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
            self.duration_value.setText("-")
            self.metadata_player.setSource(QUrl.fromLocalFile(file_path))
            self.audio_selected.emit(file_path)

    def update_duration(self, duration_in_milliseconds):
        """Atualiza o rótulo de duração com base na duração do áudio em milissegundos."""
        self.duration_value.setText(self.format_duration(duration_in_milliseconds))

    @staticmethod
    def format_file_size(size_in_bytes):
        """Formata o tamanho do arquivo em bytes para uma representação legível (B, KB, MB)."""
        if size_in_bytes < 1024:
            return f"{size_in_bytes} B"
        if size_in_bytes < 1024 * 1024:
            return f"{size_in_bytes / 1024:.1f} KB"
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def format_duration(duration_in_milliseconds):
        """Formata a duração em milissegundos para o formato "mm:ss"."""
        total_seconds = max(0, duration_in_milliseconds // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
