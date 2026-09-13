# Guia do Cliente (PySide6)

Este guia é para a parte do **cliente**. O servidor já está pronto e rodando; aqui está tudo que você
precisa para ligar a GUI nele.

- Referência completa das rotas: [`API.md`](API.md)
- Servidor no ar: `http://<ip-do-servidor>:8000` (documentação interativa em `/docs`)

---

## 1. O que o cliente precisa ter (checklist do trabalho)

| Requisito do trabalho | Como fazer na API |
|---|---|
| Selecionar um arquivo de áudio | `QFileDialog.getOpenFileName` |
| Enviar o áudio indicando o processamento | `POST /audios/upload` (multipart) |
| Reproduzir o áudio original | `GET /audios/{id}/original` |
| Reproduzir o áudio processado | `GET /audios/{id}/processed` |
| Exibir histórico de enviados/processados | `GET /audios/` |
| Exibir duração, formato e tamanho | campos `duration_sec`, `original_ext`, `size_bytes` da resposta do upload / histórico |
| Mostrar a forma de onda (extra) | `GET /audios/{id}/waveform` |
| Mostrar os metadados complementares (extra) | `GET /audios/{id}/meta` |
| Excluir (vai para a lixeira) | `DELETE /audios/{id}` |
| Restaurar / excluir de vez | `POST /trash/{id}/restore`, `GET /trash/` |

---

## 2. Preparando o ambiente

No **computador cliente** (máquina diferente da do servidor):

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install PySide6 requests
```

Ajuste no código o IP do computador onde o servidor está rodando:

```python
BASE_URL = "http://192.168.0.10:8000"   # troque pelo IP do servidor
```

> No servidor, o `docker compose up` publica a porta 8000. Se a conexão for recusada, verifique o
> firewall do Windows/Linux na porta 8000 e se as duas máquinas estão na mesma rede.

---

## 3. Cliente da API (copie para o seu projeto)

Sugestão de arquivo `client/app/api.py`. Ele centraliza as chamadas HTTP e transforma os erros do
servidor em exceções com mensagem legível.

```python
"""Camada de acesso à API do servidor de áudio."""

import os

import requests


class ApiError(Exception):
    """Erro devolvido pelo servidor (ou falha de conexão)."""

    def __init__(self, mensagem: str, status_code: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    # Utilidades
    # ------------------------------------------------------------------ #
    def url(self, caminho: str) -> str:
        """URL absoluta a partir de uma URL relativa devolvida pela API."""
        return f"{self.base_url}{caminho}"

    def _tratar(self, resposta: requests.Response):
        if resposta.ok:
            return resposta

        detalhe = f"HTTP {resposta.status_code}"
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = None

        if isinstance(corpo, dict) and "detail" in corpo:
            detalhe = corpo["detail"]
            if isinstance(detalhe, list):  # erros de validação (422)
                detalhe = "; ".join(
                    f"{' -> '.join(str(p) for p in erro.get('loc', []))}: {erro.get('msg')}"
                    for erro in detalhe
                )
        elif corpo is not None:
            detalhe = str(corpo)

        raise ApiError(str(detalhe), resposta.status_code)

    def _executar(self, metodo: str, caminho: str, **kwargs):
        try:
            resposta = self.session.request(
                metodo, self.url(caminho), timeout=self.timeout, **kwargs
            )
        except requests.RequestException as erro:
            raise ApiError(
                f"Não foi possível falar com o servidor ({self.base_url}). {erro}"
            ) from erro

        return self._tratar(resposta)

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #
    def health(self) -> dict:
        return self._executar("GET", "/health").json()

    def processing_types(self) -> list[dict]:
        return self._executar("GET", "/audios/processing-types").json()

    def list_audios(self, **filtros) -> list[dict]:
        filtros = {chave: valor for chave, valor in filtros.items() if valor not in (None, "")}
        return self._executar("GET", "/audios/", params=filtros).json()

    def get_audio(self, audio_id: str) -> dict:
        return self._executar("GET", f"/audios/{audio_id}").json()

    def metadata(self, audio_id: str) -> dict:
        return self._executar("GET", f"/audios/{audio_id}/meta").json()

    def upload(self, caminho_arquivo: str, processing_type: str, **parametros) -> dict:
        """Envia o áudio. Só os parâmetros do processamento escolhido são usados."""
        dados = {"processing_type": processing_type}
        dados.update({chave: valor for chave, valor in parametros.items() if valor is not None})

        with open(caminho_arquivo, "rb") as arquivo:
            files = {
                "file": (
                    os.path.basename(caminho_arquivo),
                    arquivo,
                    "application/octet-stream",
                )
            }
            resposta = self._executar("POST", "/audios/upload", files=files, data=dados)

        return resposta.json()

    def excluir(self, audio_id: str) -> dict:
        return self._executar("DELETE", f"/audios/{audio_id}").json()

    def listar_lixeira(self) -> list[dict]:
        return self._executar("GET", "/trash/").json()

    def restaurar(self, audio_id: str) -> dict:
        return self._executar("POST", f"/trash/{audio_id}/restore").json()

    def baixar_audio(self, audio: dict, tipo: str, destino: str) -> str:
        """Baixa o original ou o processado e devolve o caminho local do arquivo.

        Baixar antes de tocar deixa a reprodução fluida e o 'seek' funcionando.
        """
        chave = "original_url" if tipo == "original" else "processed_url"
        resposta = self._executar("GET", audio[chave])

        with open(destino, "wb") as arquivo:
            for bloco in resposta.iter_content(chunk_size=1024 * 64):
                arquivo.write(bloco)

        return destino

    def baixar_waveform(self, audio: dict) -> bytes:
        return self._executar("GET", audio["waveform_url"]).content
```

---

## 4. Chamadas HTTP sem travar a interface

Qualquer chamada de rede pode demorar (upload de um arquivo grande, processamento no servidor). Rode
sempre **fora da thread da GUI**, com `QThreadPool`:

```python
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class SinaisTarefa(QObject):
    concluido = Signal(object)
    erro = Signal(str)


class Tarefa(QRunnable):
    """Roda uma função Python em uma thread do pool e devolve o resultado por sinal."""

    def __init__(self, funcao, *args, **kwargs):
        super().__init__()
        self.funcao = funcao
        self.args = args
        self.kwargs = kwargs
        self.sinais = SinaisTarefa()

    def run(self):
        try:
            self.sinais.concluido.emit(self.funcao(*self.args, **self.kwargs))
        except Exception as erro:  # noqa: BLE001 - queremos mostrar qualquer falha na tela
            self.sinais.erro.emit(str(erro))


POOL = QThreadPool.globalInstance()


def executar_em_background(funcao, ao_concluir=None, ao_falhar=None):
    tarefa = Tarefa(funcao)

    if ao_concluir is not None:
        tarefa.sinais.concluido.connect(ao_concluir)

    if ao_falhar is not None:
        tarefa.sinais.erro.connect(ao_falhar)

    POOL.start(tarefa)
    return tarefa
```

Uso:

```python
executar_em_background(
    cliente.upload,
    ao_concluir=self._upload_concluido,
    ao_falhar=self._mostrar_erro,
)
```

---

## 5. Telas

### 5.1 Escolher o arquivo e o processamento

```python
def escolher_arquivo(self):
    caminho, _ = QFileDialog.getOpenFileName(
        self,
        "Escolha um arquivo de áudio",
        "",
        "Áudio (*.wav *.mp3 *.ogg *.oga *.flac *.m4a *.aac *.opus *.wma *.aiff *.aif *.webm)",
    )

    if not caminho:
        return

    self.campo_arquivo.setText(caminho)
    tamanho = os.path.getsize(caminho)
    self.rotulo_local.setText(
        f"{os.path.basename(caminho)} - {tamanho / 1024 / 1024:.2f} MB"
    )
```

O combo box de processamentos pode ser preenchido pela própria API
(`GET /audios/processing-types`), assim o cliente não fica com valores fixos:

```python
def carregar_processamentos(self):
    def preencher(tipos):
        self.combo_processamento.clear()

        for tipo in tipos:
            # guardamos a chave ("volume", "mono", ...) em cada item
            self.combo_processamento.addItem(f"{tipo['label']} ({tipo['key']})", tipo["key"])

    executar_em_background(self.cliente.processing_types, ao_concluir=preencher)

def processamento_escolhido(self) -> str:
    return self.combo_processamento.currentData()
```

Mostre na tela só os parâmetros do processamento selecionado (`loudness_target` para volume,
`speed_factor` para speed, `bitrate` para bitrate, `target_format` para format). Os padrões do servidor
são: `-16.0` LUFS, `1.5`, `64k`, `wav`.

```python
def enviar(self):
    caminho = self.campo_arquivo.text().strip()

    if not caminho:
        QMessageBox.warning(self, "Atenção", "Escolha um arquivo de áudio primeiro.")
        return

    processamento = self.processamento_escolhido()

    parametros = {}
    if processamento == "volume":
        parametros["loudness_target"] = self.spin_loudness.value()
    elif processamento == "speed":
        parametros["speed_factor"] = self.spin_velocidade.value()
    elif processamento == "bitrate":
        parametros["bitrate"] = self.edit_bitrate.text().strip() or "64k"
    elif processamento == "format":
        parametros["target_format"] = self.combo_formato.currentText()

    self.botao_enviar.setEnabled(False)
    self.statusBar().showMessage("Enviando e processando no servidor...")

    def concluir(audio):
        self.botao_enviar.setEnabled(True)
        self.statusBar().showMessage(f"Áudio enviado: {audio['id']}", 8000)
        self._mostrar_info_audio(audio)      # duração, formato, tamanho, canais...
        self.atualizar_historico()
        self.selecionar_audio(audio)

    executar_em_background(
        lambda: self.cliente.upload(caminho, processamento, **parametros),
        ao_concluir=concluir,
        ao_falhar=self._erro,
    )
```

> Use `lambda: self.cliente.upload(caminho, processamento, **parametros)` quando precisar passar
> argumentos. Lembre-se: a lambda roda na thread do pool, então não toque em widgets dentro dela.

### 5.2 Informações básicas do áudio

Depois do envio (ou ao selecionar um item do histórico) você tem tudo pronto na resposta:

```python
def _mostrar_info_audio(self, audio: dict):
    duracao = audio.get("duration_sec") or 0
    minutos, segundos = divmod(int(duracao), 60)

    self.rotulo_info.setText(
        f"Nome: {audio['original_name']}\n"
        f"Duração: {minutos:02d}:{segundos:02d} ({duracao:.2f}s)\n"
        f"Formato: .{audio['original_ext']} -> .{audio.get('processed_ext', audio['original_ext'])}\n"
        f"Tamanho: {audio['size_bytes'] / 1024:.1f} KB\n"
        f"Taxa de amostragem: {audio.get('sample_rate')} Hz\n"
        f"Canais: {audio.get('channels')}\n"
        f"Bitrate: {round((audio.get('bitrate') or 0) / 1000)} kbps\n"
        f"Processamento: {audio['processing_type']} {audio.get('processing_params') or ''}\n"
        f"UUID: {audio['id']}"
    )
```

### 5.3 Histórico

`GET /audios/` devolve uma lista de objetos; jogue em um `QTableWidget`:

```python
def atualizar_historico(self):
    executar_em_background(
        self.cliente.list_audios,
        ao_concluir=self._preencher_tabela,
        ao_falhar=self._erro,
    )

def _preencher_tabela(self, audios: list[dict]):
    self.tabela.setRowCount(len(audios))
    self.audios_na_tabela = audios

    for linha, audio in enumerate(audios):
        duracao = audio.get("duration_sec") or 0
        valores = [
            audio["original_name"],
            audio["processing_type"],
            f"{int(duracao // 60):02d}:{int(duracao % 60):02d}",
            str(audio.get("channels") or "-"),
            f"{audio['size_bytes'] / 1024:.0f} KB",
            (audio.get("created_at") or "")[:19].replace("T", " "),
        ]

        for coluna, valor in enumerate(valores):
            self.tabela.setItem(linha, coluna, QTableWidgetItem(valor))

    self.tabela.resizeColumnsToContents()
```

Se quiser permitir excluir do histórico (vai para a lixeira), use `DELETE /audios/{id}`; para ver a
lixeira, `GET /trash/` e `POST /trash/{id}/restore`.

### 5.4 Reprodução (original e processado)

`QMediaPlayer` (Qt6) precisa de `QAudioOutput`. O mais robusto é baixar o arquivo para uma pasta
temporária e tocar pelo caminho local:

```python
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

# no __init__ da janela:
self.player = QMediaPlayer(self)
self.saida_audio = QAudioOutput(self)
self.player.setAudioOutput(self.saida_audio)
self.saida_audio.setVolume(0.9)
self.pasta_temp = tempfile.mkdtemp(prefix="audio_cliente_")

def tocar(self, tipo: str):
    audio = self.audio_selecionado

    if audio is None:
        QMessageBox.information(self, "Atenção", "Selecione um áudio no histórico.")
        return

    extensao = audio["original_ext"] if tipo == "original" else audio.get("processed_ext", "wav")
    destino = os.path.join(self.pasta_temp, f"{audio['id']}_{tipo}.{extensao}")

    self.statusBar().showMessage(f"Baixando o áudio {tipo}...")

    def concluir(caminho):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(caminho))
        self.player.play()
        self.statusBar().showMessage(f"Reproduzindo o áudio {tipo}.", 5000)

    executar_em_background(
        lambda: self.cliente.baixar_audio(audio, tipo, destino),
        ao_concluir=concluir,
        ao_falhar=self._erro,
    )

def parar(self):
    self.player.stop()
```

Ligar aos botões:

```python
self.botao_original.clicked.connect(lambda: self.tocar("original"))
self.botao_processado.clicked.connect(lambda: self.tocar("processed"))
self.botao_parar.clicked.connect(self.parar)
```

> Se preferir tocar direto da URL (sem baixar), use
> `self.player.setSource(QUrl(self.cliente.url(audio["original_url"])))`. Funciona, mas o *seek* pode
> demorar, porque o Qt faz requisições `Range` durante a reprodução.

### 5.5 Forma de onda (opcional, mas rende pontos na apresentação)

```python
from PySide6.QtGui import QPixmap

def selecionar_audio(self, audio: dict):
    self.audio_selecionado = audio
    self._mostrar_info_audio(audio)

    def mostrar(png: bytes):
        imagem = QPixmap()
        imagem.loadFromData(png)
        self.label_waveform.setPixmap(
            imagem.scaledToWidth(600, Qt.SmoothTransformation)
        )

    executar_em_background(
        lambda: self.cliente.baixar_waveform(audio),
        ao_concluir=mostrar,
        ao_falhar=lambda msg: self.label_waveform.setText(f"Waveform indisponível: {msg}"),
    )
```

---

## 6. Esqueleto completo (`client/app/main.py`)

Ponto de partida funcional com seleção de arquivo, processamento, envio, histórico, reprodução e
waveform. Copie, ajuste `BASE_URL` e evolua o visual à vontade.

```python
import os
import sys
import tempfile

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from api import ApiClient  # arquivo api.py desta mesma pasta

BASE_URL = "http://192.168.0.10:8000"   # <-- troque pelo IP do computador servidor


class SinaisTarefa(QObject):
    concluido = Signal(object)
    erro = Signal(str)


class Tarefa(QRunnable):
    def __init__(self, funcao):
        super().__init__()
        self.funcao = funcao
        self.sinais = SinaisTarefa()

    def run(self):
        try:
            self.sinais.concluido.emit(self.funcao())
        except Exception as erro:  # noqa: BLE001 - a mensagem vai para a tela do usuário
            self.sinais.erro.emit(str(erro))


def em_background(funcao, ao_concluir, ao_falhar):
    tarefa = Tarefa(funcao)
    tarefa.sinais.concluido.connect(ao_concluir)
    tarefa.sinais.erro.connect(ao_falhar)
    QThreadPool.globalInstance().start(tarefa)
    return tarefa


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cliente de Processamento de Áudio")
        self.resize(1000, 720)

        self.cliente = ApiClient(BASE_URL)
        self.audios = []
        self.audio_selecionado = None
        self.pasta_temp = tempfile.mkdtemp(prefix="audio_cliente_")

        # Player
        self.player = QMediaPlayer(self)
        self.saida_audio = QAudioOutput(self)
        self.player.setAudioOutput(self.saida_audio)
        self.saida_audio.setVolume(0.9)

        self._montar_interface()
        self._carregar_processamentos()
        self.atualizar_historico()

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #
    def _montar_interface(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- envio ---
        self.campo_arquivo = QLineEdit(readOnly=True)
        botao_escolher = QPushButton("Escolher arquivo...")
        botao_escolher.clicked.connect(self.escolher_arquivo)

        linha_arquivo = QHBoxLayout()
        linha_arquivo.addWidget(self.campo_arquivo)
        linha_arquivo.addWidget(botao_escolher)
        layout.addLayout(linha_arquivo)

        self.combo_processamento = QComboBox()

        self.spin_loudness = QDoubleSpinBox()
        self.spin_loudness.setRange(-40.0, 0.0)
        self.spin_loudness.setValue(-16.0)
        self.spin_loudness.setSuffix(" LUFS")

        self.spin_velocidade = QDoubleSpinBox()
        self.spin_velocidade.setRange(0.5, 2.0)
        self.spin_velocidade.setSingleStep(0.05)
        self.spin_velocidade.setValue(1.5)
        self.spin_velocidade.setSuffix("x")

        self.edit_bitrate = QLineEdit("64k")

        self.combo_formato = QComboBox()
        self.combo_formato.addItems(["wav", "mp3", "ogg", "flac", "m4a", "opus"])

        formulario = QFormLayout()
        formulario.addRow("Processamento:", self.combo_processamento)
        formulario.addRow("Volume alvo:", self.spin_loudness)
        formulario.addRow("Velocidade:", self.spin_velocidade)
        formulario.addRow("Bitrate:", self.edit_bitrate)
        formulario.addRow("Formato de saída:", self.combo_formato)
        layout.addLayout(formulario)

        self.botao_enviar = QPushButton("Enviar para o servidor")
        self.botao_enviar.clicked.connect(self.enviar)
        layout.addWidget(self.botao_enviar)

        # --- informações ---
        self.rotulo_info = QLabel("Nenhum áudio selecionado.")
        self.rotulo_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.rotulo_info)

        # --- reprodução ---
        self.botao_original = QPushButton("▶ Tocar original")
        self.botao_processado = QPushButton("▶ Tocar processado")
        self.botao_parar = QPushButton("■ Parar")
        self.botao_original.clicked.connect(lambda: self.tocar("original"))
        self.botao_processado.clicked.connect(lambda: self.tocar("processed"))
        self.botao_parar.clicked.connect(self.player.stop)

        linha_botoes = QHBoxLayout()
        linha_botoes.addWidget(self.botao_original)
        linha_botoes.addWidget(self.botao_processado)
        linha_botoes.addWidget(self.botao_parar)
        layout.addLayout(linha_botoes)

        self.label_waveform = QLabel("Selecione um áudio no histórico para ver a forma de onda.")
        self.label_waveform.setMinimumHeight(140)
        layout.addWidget(self.label_waveform)

        # --- histórico ---
        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(
            ["Nome", "Processamento", "Duração", "Canais", "Tamanho", "Enviado em"]
        )
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.itemSelectionChanged.connect(self._linha_selecionada)
        layout.addWidget(self.tabela)

        botao_atualizar = QPushButton("🔄 Atualizar histórico")
        botao_atualizar.clicked.connect(self.atualizar_historico)
        layout.addWidget(botao_atualizar)

    # ------------------------------------------------------------------ #
    # Ações
    # ------------------------------------------------------------------ #
    def escolher_arquivo(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolha um arquivo de áudio", "",
            "Áudio (*.wav *.mp3 *.ogg *.oga *.flac *.m4a *.aac *.opus *.wma *.aiff *.aif *.webm)",
        )

        if caminho:
            self.campo_arquivo.setText(caminho)
            self.rotulo_info.setText(
                f"Arquivo local: {os.path.basename(caminho)} "
                f"({os.path.getsize(caminho) / 1024:.1f} KB)"
            )

    def _erro(self, mensagem: str):
        self.botao_enviar.setEnabled(True)
        self.statusBar().showMessage("Erro.", 5000)
        QMessageBox.critical(self, "Erro", mensagem)

    def _carregar_processamentos(self):
        def preencher(tipos):
            for tipo in tipos:
                self.combo_processamento.addItem(f"{tipo['label']}", tipo["key"])

        em_background(self.cliente.processing_types, preencher, self._erro)

    def enviar(self):
        caminho = self.campo_arquivo.text().strip()

        if not caminho:
            QMessageBox.warning(self, "Atenção", "Escolha um arquivo de áudio primeiro.")
            return

        processamento = self.combo_processamento.currentData()
        parametros = {}

        if processamento == "volume":
            parametros["loudness_target"] = self.spin_loudness.value()
        elif processamento == "speed":
            parametros["speed_factor"] = self.spin_velocidade.value()
        elif processamento == "bitrate":
            parametros["bitrate"] = self.edit_bitrate.text().strip() or "64k"
        elif processamento == "format":
            parametros["target_format"] = self.combo_formato.currentText()

        self.botao_enviar.setEnabled(False)
        self.statusBar().showMessage("Enviando e processando no servidor...")

        def concluir(audio):
            self.botao_enviar.setEnabled(True)
            self.statusBar().showMessage(f"Concluído! UUID: {audio['id']}", 10000)
            self.atualizar_historico()
            self.selecionar_audio(audio)

        em_background(
            lambda: self.cliente.upload(caminho, processamento, **parametros),
            concluir,
            self._erro,
        )

    def atualizar_historico(self):
        em_background(self.cliente.list_audios, self._preencher_tabela, self._erro)

    def _preencher_tabela(self, audios):
        self.audios = audios
        self.tabela.setRowCount(len(audios))

        for linha, audio in enumerate(audios):
            duracao = audio.get("duration_sec") or 0
            valores = [
                audio["original_name"],
                audio["processing_type"],
                f"{int(duracao // 60):02d}:{int(duracao % 60):02d}",
                str(audio.get("channels") or "-"),
                f"{audio['size_bytes'] / 1024:.0f} KB",
                (audio.get("created_at") or "")[:19].replace("T", " "),
            ]

            for coluna, valor in enumerate(valores):
                self.tabela.setItem(linha, coluna, QTableWidgetItem(str(valor)))

        self.tabela.resizeColumnsToContents()

    def _linha_selecionada(self):
        linhas = self.tabela.selectionModel().selectedRows()

        if linhas and self.audios:
            self.selecionar_audio(self.audios[linhas[0].row()])

    def selecionar_audio(self, audio):
        self.audio_selecionado = audio
        duracao = audio.get("duration_sec") or 0

        self.rotulo_info.setText(
            f"Arquivo: {audio['original_name']}\n"
            f"Duração: {duracao:.2f}s | Formato: .{audio['original_ext']} -> "
            f".{audio.get('processed_ext', audio['original_ext'])} | "
            f"Tamanho: {audio['size_bytes'] / 1024:.1f} KB\n"
            f"Canais: {audio.get('channels')} | Taxa de amostragem: {audio.get('sample_rate')} Hz | "
            f"Bitrate: {round((audio.get('bitrate') or 0) / 1000)} kbps\n"
            f"Processamento: {audio['processing_type']} {audio.get('processing_params') or ''}\n"
            f"UUID: {audio['id']}"
        )

        em_background(
            lambda: self.cliente.baixar_waveform(audio),
            self._mostrar_waveform,
            lambda _: self.label_waveform.setText("Waveform indisponível."),
        )

    def _mostrar_waveform(self, png: bytes):
        imagem = QPixmap()
        imagem.loadFromData(png)
        self.label_waveform.setPixmap(imagem.scaledToWidth(900, Qt.SmoothTransformation))

    def tocar(self, tipo: str):
        audio = self.audio_selecionado

        if audio is None:
            QMessageBox.information(self, "Atenção", "Selecione um áudio no histórico.")
            return

        extensao = audio["original_ext"] if tipo == "original" else audio.get("processed_ext", "wav")
        destino = os.path.join(self.pasta_temp, f"{audio['id']}_{tipo}.{extensao}")
        self.statusBar().showMessage(f"Baixando o áudio {tipo}...")

        def concluir(caminho):
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(caminho))
            self.player.play()
            self.statusBar().showMessage(f"Reproduzindo o áudio {tipo}.", 5000)

        em_background(lambda: self.cliente.baixar_audio(audio, tipo, destino), concluir, self._erro)


def main():
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

---

## 7. Dicas e armadilhas

- **Nunca** faça `requests.post` direto no clique de um botão sem thread: a janela congela e o usuário
  acha que travou. Use o `Tarefa`/`em_background` acima.
- **Dentro da lambda não mexa em widgets**: só dentro dos callbacks `ao_concluir` / `ao_falhar`, que
  rodam na thread da GUI.
- **Envie apenas os parâmetros do processamento escolhido.** O servidor valida todos os
  campos enviados (mesmo os que não usa): `speed_factor` fora de 0.5–2.0, `bitrate` fora do
  padrão `<kbps>k` ou `target_format` desconhecido geram `422`, independentemente do
  `processing_type`. O que você não enviar assume o padrão do servidor (veja
  `GET /audios/processing-types`).
- **Erros do servidor já vêm com mensagem pronta em português** (`{"detail": "..."}`); mostre no
  `QMessageBox` em vez de só "falhou".
- **Antes do upload** você só conhece nome e tamanho do arquivo local. Duração, canais, taxa de
  amostragem e bitrate chegam na resposta do `POST /audios/upload`.
- **Extensão do processado**: em `bitrate` um arquivo WAV de entrada sai como MP3 e em `format` a
  extensão é a que você escolher. Use sempre `processed_ext` da resposta.
- **Imagens**: carregue a waveform com `QPixmap.loadFromData` (bytes), nunca passando o caminho de uma
  URL HTTP direto.
- **Ao fechar a janela**, pare o player e (se quiser) apague a pasta temporária:
  ```python
  def closeEvent(self, evento):
      self.player.stop()
      shutil.rmtree(self.pasta_temp, ignore_errors=True)
      super().closeEvent(evento)
  ```
- **Servidor fora do ar**: chame `cliente.health()` na inicialização e mostre um aviso em vez de deixar
  a tela vazia sem explicação.
- **Ambiente de demonstração**: confirme o IP do servidor antes de apresentar
  (`ipconfig` no servidor) e teste o upload de um arquivo grande com antecedência.
