from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class Waveform(QWidget):
    """Forma de onda do áudio com o indicador da posição de reprodução.

    Mostra a imagem gerada pelo servidor (``waveform-original.png`` ou
    ``waveform-processed.png``). Enquanto nenhuma imagem foi recebida, desenha uma
    pré-visualização genérica, para o player não ficar vazio.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = self.create_preview_samples()
        self.position_ratio = 0.0
        self.image = None
        self.scaled_image = None
        self.setMinimumHeight(80)

    @staticmethod
    def create_preview_samples():
        """Cria uma lista de amostras de forma de onda de pré-visualização para exibição quando nenhum áudio real estiver disponível."""
        return [
            0.18, 0.32, 0.52, 0.78, 0.46, 0.25, 0.16, 0.38,
            0.68, 0.88, 0.56, 0.28, 0.18, 0.35, 0.62, 0.44,
            0.22, 0.34, 0.72, 0.94, 0.58, 0.36, 0.2, 0.42,
            0.64, 0.82, 0.48, 0.27, 0.18, 0.4, 0.7, 0.5,
        ]

    def set_samples(self, samples):
        """Define as amostras de forma de onda a serem exibidas e atualiza a exibição."""
        self.samples = list(samples) or self.create_preview_samples()
        self.update()

    def set_image(self, image_data):
        """Mostra a imagem de forma de onda recebida do servidor.

        Sem dados válidos (ou com ``None``) volta para a pré-visualização genérica,
        o que também limpa a forma de onda de um áudio anterior.
        """
        image = QPixmap()

        if image_data and image.loadFromData(image_data) and not image.isNull():
            self.image = image
        else:
            self.image = None

        self.scaled_image = None
        self.update()

    def set_position(self, position, duration):
        """Define a posição atual de reprodução como uma proporção da duração total e atualiza a exibição."""
        self.position_ratio = position / duration if duration > 0 else 0.0
        self.position_ratio = max(0.0, min(1.0, self.position_ratio))
        self.update()

    def resizeEvent(self, event):
        """Descarta a imagem redimensionada quando o widget muda de tamanho."""
        self.scaled_image = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        """Renderiza a forma de onda e o indicador de posição atual na tela."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().alternateBase().color())

        if self.image is None:
            self.draw_preview(painter)
        else:
            self.draw_image(painter)

        self.draw_position(painter)

    def draw_preview(self, painter):
        """Desenha as barras de pré-visualização quando não há imagem do servidor."""
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

    def draw_image(self, painter):
        """Desenha a imagem do servidor ocupando toda a largura e centralizada na altura.

        A imagem é maior que o widget (1200x400), então a parte que sobra é cortada
        pelo próprio Qt — o que mantém a proporção da onda sem achatar as barras.
        """
        if self.scaled_image is None:
            self.scaled_image = self.image.scaledToWidth(
                max(1, self.width()), Qt.TransformationMode.SmoothTransformation
            )

        y = (self.height() - self.scaled_image.height()) // 2
        painter.drawPixmap(0, y, self.scaled_image)

    def draw_position(self, painter):
        """Desenha a linha vertical da posição atual da reprodução."""
        indicator_x = self.position_ratio * self.width()
        painter.setPen(QPen(self.palette().brightText().color(), 1.5))
        painter.drawLine(indicator_x, 2, indicator_x, self.height() - 2)
