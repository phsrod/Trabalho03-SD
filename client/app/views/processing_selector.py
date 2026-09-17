from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
)


class ProcessingSection(QGroupBox):

    def __init__(self, parent=None):
        super().__init__("Processamento", parent)

        layout = QFormLayout(self)

        self.processing_combo = QComboBox()
        self.processing_combo.addItem("Selecione o processamento", "")
        self.processing_combo.addItem("Normalização de volume", "volume")
        self.processing_combo.addItem("Conversão para mono", "mono")
        self.processing_combo.addItem("Alteração da velocidade", "speed")
        self.processing_combo.addItem("Redução da taxa de bits", "bitrate")
        self.processing_combo.addItem("Conversão de formato", "format")
        self.processing_combo.currentIndexChanged.connect(self.update_processing_parameters)
        layout.addRow("Processamento:", self.processing_combo)

        self.speed_label = QLabel("Velocidade:")
        self.speed_value = QDoubleSpinBox()
        self.speed_value.setRange(0.5, 2.0)
        self.speed_value.setSingleStep(0.05)
        self.speed_value.setValue(1.5)
        self.speed_value.setSuffix("x")
        layout.addRow(self.speed_label, self.speed_value)

        self.target_format_label = QLabel("Formato:")
        self.target_format_combo = QComboBox()
        self.target_format_combo.addItems(["WAV", "MP3", "OGG", "FLAC", "M4A", "OPUS"])
        layout.addRow(self.target_format_label, self.target_format_combo)

        self.process_button = QPushButton("Processar áudio")
        layout.addRow("", self.process_button)

        self.update_processing_parameters()

    def update_processing_parameters(self):
        processing_type = self.processing_combo.currentData()
        show_speed = processing_type == "speed"
        show_format = processing_type == "format"

        self.speed_label.setVisible(show_speed)
        self.speed_value.setVisible(show_speed)
        self.target_format_label.setVisible(show_format)
        self.target_format_combo.setVisible(show_format)
