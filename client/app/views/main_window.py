from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from views.file_selector import FileSelector
from views.processing_selector import ProcessingSection


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

        self.file_section = FileSelector()
        layout.addWidget(self.file_section)

        self.processing_section = ProcessingSection()
        layout.addWidget(self.processing_section)

        layout.addStretch()
