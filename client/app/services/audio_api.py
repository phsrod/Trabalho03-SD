import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QFile, QIODevice, QObject, QUrl, Signal
from PySide6.QtNetwork import (
    QHttpMultiPart,
    QHttpPart,
    QNetworkAccessManager,
    QNetworkRequest,
)


class AudioApi(QObject):
    history_loaded = Signal(list)
    upload_succeeded = Signal(dict)
    request_failed = Signal(str)

    def __init__(self, base_url="http://127.0.0.1:8000", parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.network_manager = QNetworkAccessManager(self)
        self._active_reply = None
        self._active_upload = None

    def upload_audio(self, file_path, processing_type, speed_factor=1.5, target_format="wav"):
        """Envia um áudio e os parâmetros de processamento para a API."""
        audio_file = Path(file_path)
        if not audio_file.is_file():
            self.request_failed.emit("Arquivo de áudio não encontrado.")
            return

        multipart = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)

        file_part = QHttpPart()
        file_part.setHeader(
            QNetworkRequest.KnownHeaders.ContentDispositionHeader,
            f'form-data; name="file"; filename="{audio_file.name}"',
        )
        file_part.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/octet-stream",
        )
        file_device = QFile(str(audio_file), multipart)
        if not file_device.open(QIODevice.OpenModeFlag.ReadOnly):
            self.request_failed.emit("Não foi possível abrir o arquivo de áudio.")
            multipart.deleteLater()
            return
        file_part.setBodyDevice(file_device)
        multipart.append(file_part)

        self.append_form_field(multipart, "processing_type", processing_type)
        self.append_form_field(multipart, "speed_factor", str(speed_factor))
        self.append_form_field(multipart, "target_format", target_format.lower())

        request = QNetworkRequest(QUrl(f"{self.base_url}/audios/upload"))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            QByteArray(b"multipart/form-data; boundary=") + multipart.boundary(),
        )
        self._active_upload = multipart
        reply = self.network_manager.post(request, multipart)
        multipart.setParent(reply)
        reply.finished.connect(lambda: self._handle_upload_response(reply))

    @staticmethod
    def append_form_field(multipart, name, value):
        """Adiciona um campo de formulário ao objeto QHttpMultiPart."""
        part = QHttpPart()
        part.setHeader(
            QNetworkRequest.KnownHeaders.ContentDispositionHeader,
            f'form-data; name="{name}"',
        )
        part.setBody(str(value).encode())
        multipart.append(part)

    def _handle_upload_response(self, reply):
        """Manipula a resposta do servidor após o upload de áudio."""
        response_body = bytes(reply.readAll())
        status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        request_succeeded = status_code is not None and 200 <= status_code < 300
        if reply.error() and not request_succeeded:
            details = response_body.decode("utf-8", errors="replace").strip()
            message = f"HTTP {status_code}: {details}" if status_code else details
            self.request_failed.emit(message or reply.errorString())
        else:
            try:
                self.upload_succeeded.emit(json.loads(response_body))
            except (TypeError, ValueError) as error:
                self.request_failed.emit(f"Resposta inválida do servidor: {error}")
        self._active_upload = None
        reply.deleteLater()

    def fetch_history(self):
        """Solicita à API o histórico de áudios armazenados."""
        if self._active_reply is not None:
            self._active_reply.deleteLater()

        request = QNetworkRequest(QUrl(f"{self.base_url}/audios/"))
        self._active_reply = self.network_manager.get(request)
        self._active_reply.finished.connect(self._handle_history_response)

    def _handle_history_response(self):
        """Manipula a resposta do servidor após a solicitação do histórico de áudios."""
        reply = self._active_reply
        self._active_reply = None

        if reply is None:
            return

        response_body = bytes(reply.readAll())
        status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        request_succeeded = status_code is not None and 200 <= status_code < 300
        if reply.error() and not request_succeeded:
            details = response_body.decode("utf-8", errors="replace").strip()
            message = f"HTTP {status_code}: {details}" if status_code else details
            self.request_failed.emit(message or reply.errorString())
            reply.deleteLater()
            return
        try:
            records = json.loads(response_body)
        except (TypeError, ValueError) as error:
            self.request_failed.emit(f"Resposta inválida do servidor: {error}")
        else:
            self.history_loaded.emit(records)
        finally:
            reply.deleteLater()
