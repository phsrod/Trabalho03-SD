from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from services.audio_api import DEFAULT_BASE_URL, AudioApi
from views.file_selector import FileSelector
from views.history_selector import HistorySection
from views.playback_selector import PlaybackSection
from views.processing_selector import ProcessingSection


class MainWindow(QMainWindow):

    def __init__(self, base_url=DEFAULT_BASE_URL, parent=None):
        super().__init__(parent)

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

        self.audio_api = AudioApi(base_url, parent=self)
        self.processing_section.process_button.clicked.connect(self.process_audio)
        self.audio_api.upload_succeeded.connect(self.handle_upload_success)
        self.audio_api.request_failed.connect(self.handle_api_error)

        self.playback_section = PlaybackSection()
        layout.addWidget(self.playback_section)
        self.file_section.audio_selected.connect(
            self.playback_section.set_original_audio
        )
        self.audio_api.original_waveform_loaded.connect(
            self.playback_section.set_original_waveform
        )
        self.audio_api.processed_waveform_loaded.connect(
            self.playback_section.set_processed_waveform
        )

        self.history_section = HistorySection(base_url)
        layout.addWidget(self.history_section)

        layout.addStretch()

    def process_audio(self):
        """Envia o arquivo de áudio selecionado para processamento com os parâmetros especificados na seção de processamento."""
        file_path = self.file_section.selected_file_path
        if not file_path:
            self.processing_section.status_label.setText(
                "Selecione um áudio antes de processar."
            )
            return

        processing_type = self.processing_section.processing_combo.currentData()
        if not processing_type:
            self.processing_section.status_label.setText(
                "Selecione um tipo de processamento."
            )
            return

        self.processing_section.status_label.setText("Enviando áudio...")
        self.audio_api.upload_audio(
            file_path,
            processing_type,
            self.processing_section.speed_value.value(),
            self.processing_section.target_format_combo.currentText(),
        )

    def handle_upload_success(self, record):
        """Atualiza a interface após o upload bem-sucedido do áudio processado."""
        processed_url = record.get("processed_url")
        if processed_url:
            self.playback_section.set_processed_audio_url(
                f"{self.audio_api.base_url}{processed_url}"
            )
        self.audio_api.fetch_waveforms(record)
        self.processing_section.status_label.setText(
            f"Processamento concluído! Áudio processado recebido."
        )
        self.history_section.api.fetch_history()

    def handle_api_error(self, message):
        """Exibe uma mensagem de erro na seção de processamento quando a solicitação falha."""
        self.processing_section.status_label.setText(f"Erro: {message}")
