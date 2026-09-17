from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from views.file_selector import FileSelector
from views.history_selector import HistorySection
from views.playback_selector import PlaybackSection
from views.processing_selector import ProcessingSection


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Processador de Áudio")
        self.resize(960, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        title = QLabel("PROCESSADOR DE ÁUDIO")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        self.file_section = FileSelector()
        layout.addWidget(self.file_section)

        self.processing_section = ProcessingSection()
        layout.addWidget(self.processing_section)

        self.playback_section = PlaybackSection()
        layout.addWidget(self.playback_section)
        self.file_section.audio_selected.connect(
            self.playback_section.set_original_audio
        )

        self.history_section = HistorySection()
        layout.addWidget(self.history_section)

        layout.addStretch()
