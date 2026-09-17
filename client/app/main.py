import sys

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from services.audio_api import DEFAULT_BASE_URL
from views.main_window import MainWindow

CONNECTION_TIMEOUT_MS = 5000


def normalize_base_url(raw_url):
    """Normaliza o endereço informado, adicionando http:// quando o esquema não for indicado."""
    base_url = (raw_url or "").strip()
    if not base_url:
        return ""
    if not base_url.lower().startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    scheme, separator, host = base_url.rstrip("/").partition("://")
    host = host.strip("/")
    if not separator or not host:
        return ""
    return f"{scheme.lower()}://{host}"


def ask_server_url(default_url=DEFAULT_BASE_URL):
    """Solicita o endereço do servidor. Retorna string vazia se o usuário cancelar."""
    raw_url, accepted = QInputDialog.getText(
        None,
        "Conectar ao servidor",
        "Informe o endereço do servidor de áudio:\n"
        "(ex.: http://127.0.0.1:8000 ou 192.168.0.10:8000)",
        text=default_url,
    )
    if not accepted:
        return ""
    return normalize_base_url(raw_url)


def check_server_connection(base_url, timeout_ms=CONNECTION_TIMEOUT_MS):
    """Verifica com GET /health se o servidor está acessível.

    A espera acontece em um QEventLoop local, de modo que a interface continua
    respondendo enquanto o Qt aguarda a resposta da rede.
    Retorna uma tupla (conectado, mensagem_de_erro).
    """
    network_manager = QNetworkAccessManager()
    loop = QEventLoop()
    timed_out = False

    def handle_timeout():
        nonlocal timed_out
        timed_out = True
        reply.abort()
        loop.quit()

    request = QNetworkRequest(QUrl(f"{base_url}/health"))
    reply = network_manager.get(request)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(handle_timeout)
    reply.finished.connect(loop.quit)
    timeout.start(timeout_ms)
    loop.exec()
    timeout.stop()

    status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    # O sucesso é definido pelo status HTTP: no PySide6 o membro
    # QNetworkReply.NetworkError.NoError (valor 0) é avaliado como verdadeiro,
    # então "reply.error()" não serve como teste de falha.
    succeeded = (
        not timed_out
        and status_code is not None
        and 200 <= status_code < 300
    )
    if succeeded:
        message = ""
    elif timed_out:
        message = f"Tempo limite de {timeout_ms // 1000}s excedido."
    else:
        details = bytes(reply.readAll()).decode("utf-8", errors="replace").strip()
        message = f"HTTP {status_code}: {details}" if status_code else reply.errorString()
    reply.deleteLater()
    return succeeded, message


def ask_connection_failure(base_url, message):
    """Pergunta ao usuário o que fazer após uma falha de conexão."""
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Não foi possível conectar")
    box.setText(f"Não foi possível conectar ao servidor em {base_url}.")
    box.setInformativeText(f"{message}\n\nDeseja tentar novamente?")
    retry_button = box.addButton("Tentar novamente", QMessageBox.ButtonRole.AcceptRole)
    change_button = box.addButton("Alterar endereço", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(retry_button)
    box.exec()

    clicked = box.clickedButton()
    if clicked is retry_button:
        return "retry"
    if clicked is change_button:
        return "change"
    return "cancel"


def main():
    app = QApplication(sys.argv)

    base_url = ask_server_url()
    if not base_url:
        print("Nenhum endereço de servidor informado. Encerrando o cliente.")
        return 0

    while True:
        connected, message = check_server_connection(base_url)
        if connected:
            break

        action = ask_connection_failure(base_url, message)
        if action == "cancel":
            print("Conexão com o servidor cancelada. Encerrando o cliente.")
            return 0
        if action == "change":
            base_url = ask_server_url(base_url)
            if not base_url:
                print("Nenhum endereço de servidor informado. Encerrando o cliente.")
                return 0

    window = MainWindow(base_url)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
