from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget


class Waveform(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = self.create_preview_samples()
        self.position_ratio = 0.0
        self.setMinimumHeight(44)

    @staticmethod
    def create_preview_samples():
        return [
            0.18, 0.32, 0.52, 0.78, 0.46, 0.25, 0.16, 0.38,
            0.68, 0.88, 0.56, 0.28, 0.18, 0.35, 0.62, 0.44,
            0.22, 0.34, 0.72, 0.94, 0.58, 0.36, 0.2, 0.42,
            0.64, 0.82, 0.48, 0.27, 0.18, 0.4, 0.7, 0.5,
        ]

    def set_samples(self, samples):
        self.samples = list(samples) or self.create_preview_samples()
        self.update()

    def set_position(self, position, duration):
        self.position_ratio = position / duration if duration > 0 else 0.0
        self.position_ratio = max(0.0, min(1.0, self.position_ratio))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        background = self.palette().alternateBase().color()
        painter.fillRect(self.rect(), background)

        center_y = self.height() / 2
        bar_width = max(1.5, self.width() / (len(self.samples) * 1.8))
        spacing = bar_width * 0.8
        waveform_width = (bar_width + spacing) * len(self.samples)
        start_x = max(0.0, (self.width() - waveform_width) / 2)

        painter.setPen(QPen(self.palette().highlight().color(), bar_width))
        for index, amplitude in enumerate(self.samples):
            x = start_x + index * (bar_width + spacing)
            half_height = max(2.0, amplitude * (self.height() - 12) / 2)
            painter.drawLine(x, center_y - half_height, x, center_y + half_height)

        indicator_x = self.position_ratio * self.width()
        painter.setPen(QPen(self.palette().brightText().color(), 1.5))
        painter.drawLine(indicator_x, 2, indicator_x, self.height() - 2)
