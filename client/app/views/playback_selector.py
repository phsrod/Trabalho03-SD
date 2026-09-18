from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QGroupBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from views.waveform import Waveform


class PlaybackSection(QGroupBox):

    def __init__(self, parent=None):
        super().__init__("Reprodução", parent)

        layout = QVBoxLayout(self)
        self.original_player, self.original_audio_output = self.create_player()
        self.processed_player, self.processed_audio_output = self.create_player()

        original_layout, self.original_waveform, self.original_time = self.create_controls(
            "Áudio original", self.original_player
        )
        processed_layout, self.processed_waveform, self.processed_time = self.create_controls(
            "Áudio processado", self.processed_player
        )
        layout.addLayout(original_layout)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        layout.addLayout(processed_layout)

    @staticmethod
    def create_player():
        """Cria um player de áudio e um objeto de saída de áudio associados."""
        player = QMediaPlayer()
        audio_output = QAudioOutput()
        player.setAudioOutput(audio_output)
        return player, audio_output

    def create_controls(self, title, player):
        """Cria os controles de reprodução para um player de áudio específico, incluindo o título, a forma de onda e os botões de reprodução/pausa."""
        section_layout = QVBoxLayout()
        section_layout.setSpacing(6)
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_color = "#2864c7" if title == "Áudio original" else "#2e8b57"
        title_label.setStyleSheet(
            f"color: {title_color}; font-weight: bold; font-size: 14px;"
        )
        header_layout.addStretch()
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        waveform = Waveform()
        time_label = QLabel("00:00 / 00:00")
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_label.setStyleSheet("font-weight: bold;")
        player.positionChanged.connect(
            lambda position: self.update_playback_position(
                waveform, time_label, player, position
            )
        )
        player.durationChanged.connect(
            lambda duration: self.update_playback_position(
                waveform, time_label, player, player.position()
            )
        )

        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        play_button = QPushButton("Reproduzir")
        play_button.clicked.connect(player.play)
        controls_layout.addWidget(play_button)

        pause_button = QPushButton("Pausar")
        pause_button.clicked.connect(player.pause)
        controls_layout.addWidget(pause_button)
        controls_layout.addStretch()

        section_layout.addLayout(header_layout)
        waveform_layout = QHBoxLayout()
        waveform_layout.addWidget(waveform, 1)
        waveform_layout.addWidget(time_label)
        section_layout.addLayout(waveform_layout)
        section_layout.addLayout(controls_layout)
        return section_layout, waveform, time_label

    @staticmethod
    def update_playback_position(waveform, time_label, player, position):
        """Atualiza a posição da forma de onda e o rótulo de tempo com base na posição atual do player."""
        duration = player.duration()
        waveform.set_position(position, duration)
        time_label.setText(
            f"{PlaybackSection.format_time(position)} / "
            f"{PlaybackSection.format_time(duration)}"
        )

    @staticmethod
    def format_time(milliseconds):
        """Formata o tempo em milissegundos para o formato MM:SS."""
        total_seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def set_original_audio(self, file_path):
        """Define o arquivo de áudio original para reprodução.

        A forma de onda anterior é limpa: ela pertencia ao arquivo enviado antes.
        """
        self.original_waveform.set_image(None)
        self.original_player.setSource(QUrl.fromLocalFile(str(Path(file_path))))

    def set_original_waveform(self, image_data):
        """Mostra a forma de onda do áudio original gerada pelo servidor."""
        self.original_waveform.set_image(image_data)

    def set_processed_waveform(self, image_data):
        """Mostra a forma de onda do áudio processado gerada pelo servidor."""
        self.processed_waveform.set_image(image_data)

    def set_processed_audio(self, file_path):
        """Define o arquivo de áudio processado para reprodução."""
        self.processed_player.setSource(QUrl.fromLocalFile(str(Path(file_path))))

    def set_processed_audio_url(self, url):
        """Define a URL do áudio processado para reprodução."""
        self.processed_player.setSource(QUrl(url))
