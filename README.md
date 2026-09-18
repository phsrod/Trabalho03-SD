# Processamento de Áudio — Trabalho 03 (SD)

Sistema distribuído **cliente-servidor** para enviar, processar, ouvir e organizar arquivos de áudio. O cliente desktop em **PySide6** seleciona o arquivo e o processamento desejado e envia para um servidor **FastAPI**, que aplica o processamento com **FFmpeg**, guarda o original e o processado no disco, gera a forma de onda e registra os metadados no **PostgreSQL**. Projeto acadêmico da disciplina de Sistemas Distribuídos.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white) ![PySide6](https://img.shields.io/badge/PySide6-6.11.2-41CD52?logo=qt&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688?logo=fastapi&logoColor=white) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white) ![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white) ![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?logo=ffmpeg&logoColor=white) ![License](https://img.shields.io/badge/licen%C3%A7a-MPL--2.0-blue)

---

## Sumário

- [Descrição do projeto](#descrição-do-projeto)
- [Tecnologias](#tecnologias)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Execução do servidor](#execução-do-servidor)
- [Execução do cliente](#execução-do-cliente)
- [Configuração do banco de dados](#configuração-do-banco-de-dados)
- [Exemplos de processamento disponíveis](#exemplos-de-processamento-disponíveis)
- [Prints da interface](#prints-da-interface)
- [Prints da organização dos arquivos](#prints-da-organização-dos-arquivos)
- [Vídeo demonstrativo (opcional)](#vídeo-demonstrativo-opcional)
- [Licença](#licença)

---

## Descrição do projeto

O trabalho consiste em um cliente desktop que **encaminha um áudio para processamento em outro computador** e recebe de volta o resultado, o histórico e as informações do arquivo. O processamento pesado (FFmpeg) roda apenas no servidor; o cliente cuida da interface, do envio e da reprodução.

Fluxo geral:

1. O cliente seleciona um arquivo local (`.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a`, entre outros) e mostra **formato, tamanho e duração**.
2. Antes de abrir a janela, o cliente pede o **endereço do servidor** e valida a conexão com `GET /health`.
3. O usuário escolhe o **processamento** (normalização de volume, mono, velocidade, bitrate ou formato) e clica em *Processar áudio*.
4. O servidor grava o original, roda o `ffprobe`, aplica o filtro do FFmpeg, gera `waveform.png` e `meta.json`, calcula o **checksum SHA-256** e insere a linha na tabela `audios` do PostgreSQL.
5. A resposta (JSON) traz o `id` (UUID), os metadados e as **URLs** do original, do processado e da waveform — usadas pelo cliente para reproduzir e exibir o histórico.

O que o sistema entrega:

| Requisito | Como funciona |
|---|---|
| Selecionar um áudio | `QFileDialog` na seção **Arquivo** do cliente |
| Enviar indicando o processamento | `POST /audios/upload` (`multipart/form-data`) com `processing_type` |
| Reproduzir o áudio original | Player 1 do cliente (`QMediaPlayer`) a partir do arquivo local |
| Reproduzir o áudio processado | Player 2 do cliente, apontando para `GET /audios/{id}/processed` |
| Histórico de enviados/processados | `GET /audios/` em uma tabela (`QTableWidget`) |
| Duração, formato e tamanho | Colunas do histórico e a resposta do upload |
| Forma de onda (extra) | Widget de waveform com indicador da posição de reprodução |
| Metadados complementares (extra) | `GET /audios/{id}/meta` (`meta.json` com checksum e parâmetros aplicados) |
| Exclusão reversível (extra) | `DELETE /audios/{id}` move para a lixeira; `POST /trash/{id}/restore` restaura |

---

## Tecnologias

| Camada | Tecnologia | Versão | Papel |
|---|---|---|---|
| **Cliente** | Python | 3.13 | Linguagem do cliente |
| | PySide6 (Qt 6) | 6.11.2 | Interface desktop: `QtWidgets`, `QtNetwork`, `QtMultimedia` |
| **Servidor** | FastAPI | 0.141.1 | API HTTP/REST com validação e documentação automática |
| | Uvicorn | 0.52.4 | Servidor ASGI |
| | python-multipart | 0.0.32 | Leitura do upload `multipart/form-data` |
| **Processamento** | FFmpeg / FFprobe | — | Filtros de áudio, metadados e geração da waveform |
| **Persistência** | PostgreSQL | 17 | Histórico e metadados dos áudios |
| | SQLAlchemy | 2.0.52 | ORM e criação/atualização do esquema |
| | psycopg2-binary | 2.9.13 | Driver do PostgreSQL |
| **Infraestrutura** | Docker + Docker Compose | — | Sobe o servidor e o banco com um comando |
| **Armazenamento** | Sistema de arquivos | — | `server/storage/` (áudios) e `server/trash/` (lixeira) |

---

## Arquitetura

Arquitetura **cliente-servidor em camadas**, com comunicação **HTTP/REST (síncrona)** entre as duas máquinas e **persistência híbrida**: o arquivo binário fica no sistema de arquivos do servidor e os metadados no PostgreSQL. O cliente nunca toca no banco nem no disco do servidor — só usa a API.

### Visão geral

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      CLIENTE DESKTOP (PySide6 / Qt 6)                    │
│                                                                          │
│  ┌───────────────┐   ┌──────────────────┐   ┌─────────────────────────┐   │
│  │ FileSelector  │   │ ProcessingSection│   │ PlaybackSection         │   │
│  │ (QFileDialog) │   │ (combo + params) │   │ (2x QMediaPlayer +      │   │
│  └───────┬───────┘   └────────┬─────────┘   │  2 waveforms + tempo)   │   │
│          │                    │             └────────────┬────────────┘   │
│          │                    │                          │                │
│          ▼                    ▼                          ▼                │
│  ┌────────────────┐   ┌──────────────────┐   ┌─────────────────────────┐  │
│  │ MainWindow     │──▶│ AudioApi         │   │ HistorySection          │  │
│  │ (orquestração) │   │ QNetworkAccessMgr│   │ (QTableWidget)          │  │
│  └────────────────┘   └────────┬─────────┘   └────────────┬────────────┘  │
└────────────────────────────────┼──────────────────────────┼───────────────┘
                                 │  multipart + JSON        │  JSON / PNG
                                 ▼                          ▼
                        Rede local (Wi-Fi / Ethernet) — HTTP na porta 8000
                                 │                          │
┌────────────────────────────────┼──────────────────────────┼───────────────┐
│                      SERVIDOR (FastAPI + Uvicorn)         │               │
│  ┌──────────────┐                                                          │
│  │ audio_routes │──┐                                                       │
│  │ trash_routes │  │   ┌──────────────────┐   ┌────────────────────────┐   │
│  └──────┬───────┘  └──▶│ upload_service   │──▶│ audio_service          │   │
│         │              │ (pipeline)       │   │ ffprobe + FFmpeg       │   │
│         │              └────────┬─────────┘   └────────────────────────┘   │
│         │                       ▼                                          │
│         │              ┌──────────────────┐   ┌────────────────────────┐   │
│         │              │ storage_service  │──▶│ storage/<data>/<uuid>/ │   │
│         │              └──────────────────┘   │ trash/<uuid>/          │   │
│         ▼                                     └────────────────────────┘   │
│  ┌──────────────┐                                                          │
│  │ SQLAlchemy   │──▶ PostgreSQL 17 — tabela audios                         │
│  └──────────────┘                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Fluxo de um upload

```
Cliente (PySide6)                          Servidor (FastAPI)              PostgreSQL / Disco
   │                                             │                                │
   │ escolhe arquivo + processamento              │                                │
   │ POST /audios/upload (multipart)              │                                │
   │─────────────────────────────────────────────▶│                                │
   │                                             │ valida extensão e tamanho      │
   │                                             │ (400 ou 413 se inválido)       │
   │                                             │ gera UUID                      │
   │                                             │───────────────────────────────▶│ storage/<data>/<uuid>/original/
   │                                             │ ffprobe (duração, canais,      │
   │                                             │          taxa, bitrate)        │
   │                                             │ FFmpeg (processamento)         │
   │                                             │───────────────────────────────▶│ .../processed/audio.<ext>
   │                                             │ waveform-original.png          │
   │                                             │ waveform-processed.png         │
   │                                             │ meta.json                      │
   │                                             │ checksum SHA-256               │
   │                                             │───────────────────────────────▶│ INSERT INTO audios
   │ 201 Created { id, urls, metadados }         │                                │
   │◀─────────────────────────────────────────────│                                │
   │ atualiza histórico, players e waveforms      │                                │
   │ GET /audios/{id}/processed (player 2)        │                                │
   │─────────────────────────────────────────────▶│ responde o arquivo (Range/206)  │
   │ GET /audios/{id}/waveform/{tipo}             │                                │
   │─────────────────────────────────────────────▶│ responde o PNG da onda          │
```

> Se qualquer etapa falhar, o servidor **desfaz tudo**: apaga a pasta do UUID e descarta a transação, para não deixar lixo no storage nem registro órfão no banco.

### Componentes principais

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| **Cliente** | `client/app/main.py` | Solicita o endereço do servidor, valida `GET /health` e abre a janela principal |
| | `client/app/views/main_window.py` | Janela principal e orquestração das seções |
| | `client/app/services/audio_api.py` | Cliente HTTP com `QNetworkAccessManager` (upload multipart e histórico) |
| | `client/app/views/file_selector.py` | Seleção do arquivo e leitura de formato, tamanho e duração |
| | `client/app/views/processing_selector.py` | Escolha do processamento e exibição dos parâmetros correspondentes |
| | `client/app/views/playback_selector.py` | Reprodução do original e do processado (play/pause/tempo) |
| | `client/app/views/waveform.py` | Desenho da forma de onda e do indicador de posição |
| | `client/app/views/history_selector.py` | Tabela do histórico (`GET /audios/`) |
| **Servidor** | `server/src/main.py` | Aplicação FastAPI, CORS, `GET /`, `GET /health` |
| | `server/src/routes/audio_routes.py` | Upload, histórico, detalhe, reprodução, download e exclusão |
| | `server/src/routes/trash_routes.py` | Listar, restaurar, excluir definitivamente e esvaziar a lixeira |
| | `server/src/services/upload_service.py` | Pipeline do upload (validação → disco → processamento → banco) |
| | `server/src/services/audio_service.py` | Comandos do `ffprobe`/`ffmpeg` e validação de parâmetros |
| | `server/src/services/storage_service.py` | Caminhos, `meta.json`, checksum e organização de `storage/`/`trash/` |
| | `server/src/models/audio.py` | Modelo ORM da tabela `audios` |
| | `server/src/schemas/` | Contratos de entrada/saída (`AudioResponse`, `TrashItem`, `HealthResponse`…) |
| | `server/src/database.py` | Engine do SQLAlchemy, `create_all` e colunas ausentes |
| | `server/src/processing.py` | Tipos de processamento, formatos, padrões e limites |
| | `server/src/config.py` | Configurações por variáveis de ambiente |

### Endpoints da API

Documentação interativa (Swagger) em **`http://localhost:8000/docs`**.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/audios/upload` | Envia o áudio e aplica o processamento escolhido |
| `GET` | `/audios/processing-types` | Lista os processamentos disponíveis e seus parâmetros |
| `GET` | `/audios/` | Histórico (filtros: `processing_type`, `search`, `include_deleted`, `skip`, `limit`) |
| `GET` | `/audios/{id}` | Metadados de um áudio |
| `GET` | `/audios/{id}/files` | Arquivos físicos daquele áudio no disco |
| `GET` | `/audios/{id}/meta` | Conteúdo do `meta.json` |
| `GET` | `/audios/{id}/original` | Reproduz o original (suporta `Range`) |
| `GET` | `/audios/{id}/processed` | Reproduz o processado (suporta `Range`) |
| `GET` | `/audios/{id}/waveform` | Forma de onda do processado (mesma imagem de `/waveform/processed`) |
| `GET` | `/audios/{id}/waveform/original` | Forma de onda do arquivo enviado |
| `GET` | `/audios/{id}/waveform/processed` | Forma de onda do arquivo processado |
| `GET` | `/audios/{id}/download/original` | Download do original |
| `GET` | `/audios/{id}/download/processed` | Download do processado |
| `DELETE` | `/audios/{id}` | Move o áudio para a lixeira |
| `GET` | `/trash/` | Lista os itens da lixeira |
| `POST` | `/trash/{id}/restore` | Restaura um áudio da lixeira |
| `DELETE` | `/trash/{id}` | Exclui definitivamente um item |
| `DELETE` | `/trash/` | Esvazia a lixeira |
| `GET` | `/` | Resumo dos endpoints disponíveis |
| `GET` | `/health` | Estado do servidor, do banco e das pastas de armazenamento |

As **URLs da resposta são relativas** (ex.: `/audios/<uuid>/processed`); o cliente concatena com a base URL escolhida no início. Erros seguem o formato `{"detail": "mensagem em português"}`.

---

## Instalação

### Pré-requisitos

| Componente | Requisito |
|---|---|
| **Servidor** | [Docker](https://docs.docker.com/get-docker/) e Docker Compose (o FFmpeg já vem na imagem) |
| **Cliente** | [Python 3.13](https://www.python.org/downloads/) instalado |
| **Rede** | Se o servidor estiver em outra máquina, ambas precisam estar na mesma rede e a porta **8000** liberada |

### 1. Clonar o repositório

```bash
git clone https://github.com/phsrod/Trabalho03-SD.git
cd Trabalho03-SD
```

### 2. Instalar as dependências do cliente

```bash
cd client

# criar o ambiente virtual
python -m venv .venv

# ativar (Windows)
.venv\Scripts\activate
# ativar (Linux/macOS)
source .venv/bin/activate

# instalar o PySide6
pip install -r requirements.txt
```

---

## Execução do servidor

Na **raiz do projeto** (onde está o `docker-compose.yml`):

```bash
docker compose up --build
```

O comando sobe dois containers: o servidor (`audio_server`, porta **8000**) e o PostgreSQL (`audio_postgres`, porta **5433** no host). Saída esperada, em linhas gerais:

```text
audio_postgres  | database system is ready to accept connections
audio_server    | 2026-09-17 20:15:01,120 | INFO     | src.database | Banco de dados pronto.
audio_server    | 2026-09-17 20:15:01,127 | INFO     | src.main | Storage em /app/storage | lixeira em /app/trash
audio_server    | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Com o servidor no ar:

| Endereço | O que é |
|---|---|
| `http://localhost:8000` | Resumo dos endpoints (JSON) |
| `http://localhost:8000/docs` | Swagger UI — testar upload e rotas direto no navegador |
| `http://localhost:8000/health` | Estado do servidor, banco, storage e lixeira |

Para descobrir o **IP do servidor** (usado no cliente):

```bash
# Windows
ipconfig

# Linux / macOS
ip addr
# ou
ifconfig
```

Procure o IPv4 da interface Wi-Fi/Ethernet (algo como `192.168.0.10`).

> **Importante:** se o cliente estiver em outra máquina, use o **IP da rede local** do servidor — `localhost`/`127.0.0.1` só funciona quando o cliente roda na mesma máquina.

### Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/audio_db` | Conexão com o PostgreSQL |
| `STORAGE_PATH` | `server/storage` | Onde os áudios são gravados |
| `TRASH_PATH` | `server/trash` | Onde os itens excluídos ficam |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Interface e porta do servidor |
| `MAX_UPLOAD_SIZE_BYTES` | `209715200` (200 MB) | Limite do arquivo aceito no upload |

Para parar: `Ctrl+C` no terminal, ou `docker compose down` (mantém os dados). Os volumes `./server/src`, `./server/storage` e `./server/trash` são montados no container, então alterações no código recarregam sozinhas (`--reload`) e os arquivos continuam no host.

---

## Execução do cliente

Com o servidor no ar e o ambiente virtual ativo:

```bash
cd client\app      # Windows (CMD/PowerShell)
cd client/app      # Linux/macOS/Git Bash

python main.py
```

### 1. Endereço do servidor

Antes de abrir a janela, o cliente exibe o diálogo **Conectar ao servidor**:

| Comportamento | Detalhe |
|---|---|
| Valor padrão | `http://127.0.0.1:8000` |
| Aceita apenas IP e porta | `192.168.0.10:8000` vira `http://192.168.0.10:8000` automaticamente |
| Espaços | são removidos do início e do fim |
| Campo vazio ou cancelado | o cliente encerra sem abrir a janela |
| Validação | `GET /health` antes de abrir a janela principal |

Se o servidor não responder, aparece a mensagem **“Não foi possível conectar ao servidor em …”** com os botões:

- **Tentar novamente** — repete a verificação no mesmo endereço;
- **Alterar endereço** — reabre o diálogo para corrigir o IP/porta;
- **Cancelar** — encerra o cliente.

A verificação tem um tempo limite de 5 segundos e roda no mecanismo de rede do próprio Qt, então a interface não congela durante a espera.

### 2. Usando a interface

1. **Arquivo** — *Selecionar áudio* abre o `QFileDialog`; formato, tamanho e duração aparecem na seção.
2. **Processamento** — escolha o tipo; a velocidade (0,5x–2,0x) ou o formato de saída aparecem apenas quando fazem sentido. Clique em *Processar áudio*.
3. **Reprodução** — dois players independentes (*Reproduzir* / *Pausar*): o **original** toca o arquivo local e o **processado** toca direto da URL do servidor. Cada player mostra a **forma de onda real** do seu áudio (imagem gerada pelo servidor) com o tempo decorrido e o indicador de posição.
4. **Histórico** — lista os áudios do servidor (data, arquivo, processamento, duração e status); *Atualizar histórico* recarrega a lista.

> O cliente não expõe todos os parâmetros da API: a normalização de volume usa o padrão do servidor (**-16 LUFS**) e a lixeira é acessada apenas pelas rotas `/trash/` ou pelo Swagger.

O envio é feito em `multipart/form-data` por `QNetworkAccessManager`, sem travar a interface enquanto o servidor processa.

> **Firewall:** se o cliente estiver em outra máquina e a conexão for recusada, libere a porta **8000** no firewall do servidor (no Windows: *Firewall do Windows Defender → Regras de entrada → Nova regra → Porta*).

---

## Configuração do banco de dados

O PostgreSQL roda em container, com os dados em um volume Docker — ou seja, sobrevivem a `docker compose restart`. A configuração fica no `docker-compose.yml`:

| Configuração | Valor |
|---|---|
| Imagem | `postgres:17` |
| Container | `audio_postgres` |
| Banco | `audio_db` |
| Usuário / senha | `postgres` / `postgres` |
| Porta no host | `5433` → `5432` no container (evita conflito com um PostgreSQL local na 5432) |
| Volume | `postgres_data` (`/var/lib/postgresql/data`) |
| Script de inicialização | `database/init.sql` |

O `database/init.sql` é executado **na primeira criação do volume** e prepara o banco:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS audios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_name VARCHAR(255) NOT NULL,
    original_ext VARCHAR(20) NOT NULL,
    mime_type VARCHAR(100),
    size_bytes BIGINT,
    duration_sec DOUBLE PRECISION,
    sample_rate INTEGER,
    channels INTEGER,
    bitrate INTEGER,
    processing_type VARCHAR(50) NOT NULL,
    processing_params JSONB,
    checksum VARCHAR(64),
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    path_original TEXT NOT NULL,
    path_processed TEXT NOT NULL
);
```

Além do script, o servidor também garante o esquema na inicialização (`Base.metadata.create_all` + criação de colunas ausentes, com tentativas até o banco aceitar conexões). Campos de destaque:

| Coluna | Conteúdo |
|---|---|
| `processing_type` / `processing_params` | Processamento escolhido e parâmetros realmente aplicados (JSONB) |
| `checksum` | SHA-256 do arquivo original (permite comparar arquivos idênticos) |
| `path_original` / `path_processed` | Caminhos **relativos** ao storage (`2026-09-17/<uuid>/processed/audio.mp3`) |
| `deleted_at` | Preenchido apenas quando o áudio está na lixeira |
| `created_at` | Data e hora do envio (`ORDER BY created_at DESC` no histórico) |

Acessar o banco pelo container:

```bash
docker compose exec postgres psql -U postgres -d audio_db
```

Consultas úteis:

```sql
-- todos os áudios, com todas as colunas (do mais recente para o mais antigo)
SELECT * FROM audios ORDER BY created_at DESC;

-- a mesma consulta em formato vertical (\x auto faz o psql trocar sozinho
-- quando a linha não couber na tela — útil por causa do JSONB e dos caminhos)
\x auto
SELECT * FROM audios ORDER BY created_at DESC;
\x auto

-- últimos envios (só as colunas principais)
SELECT created_at, original_name, processing_type, duration_sec, channels
FROM audios ORDER BY created_at DESC LIMIT 10;

-- quantos áudios por processamento (sem contar a lixeira)
SELECT processing_type, COUNT(*) FROM audios WHERE deleted_at IS NULL GROUP BY processing_type;

-- o que está na lixeira
SELECT id, original_name, deleted_at FROM audios WHERE deleted_at IS NOT NULL;
```

Para **zerar tudo** (apaga o volume, o banco e os registros):

```bash
docker compose down -v
```

> Os arquivos enviados ficam em `server/storage/` e os excluídos em `server/trash/`. Apagar o volume do banco **não** apaga esses arquivos — para limpar também, remova as pastas manualmente.

---

## Exemplos de processamento disponíveis

Todos os processamentos rodam no servidor com **FFmpeg**. A lista completa com rótulos, descrições e parâmetros pode ser consultada em `GET /audios/processing-types`; os rótulos da tabela abaixo são os mesmos exibidos no combo do cliente.

| `processing_type` | Rótulo | Filtro / comando FFmpeg | Parâmetro | Padrão e limites | Arquivo processado |
|---|---|---|---|---|---|
| `original` | Sem processamento | cópia idêntica (`copy2`) | — | — | mesma extensão |
| `volume` | Normalização de volume | `loudnorm=I=<alvo>:TP=-1.5:LRA=11` | `loudness_target` | `-16.0` LUFS (de `-40` a `0`) | mesma extensão |
| `mono` | Conversão para mono | `-ac 1` | — | — | mesma extensão |
| `speed` | Alteração de velocidade | `atempo=<fator>` (sem mudar o tom) | `speed_factor` | `1.5` (de `0.5` a `2.0`) | mesma extensão |
| `bitrate` | Redução da taxa de bits | `-b:a <bitrate>` | `bitrate` | `64k` (formato `<kbps>k`) | mesma, se a fonte tiver perda; **MP3** se for WAV/FLAC/AIFF |
| `format` | Conversão de formato | troca de container/codec | `target_format` | `wav` (wav, mp3, ogg, flac, m4a, opus) | o formato escolhido |

Extensões aceitas no upload: `wav, mp3, ogg, oga, flac, m4a, aac, opus, wma, aiff, aif, webm` (até 200 MB). Todos os parâmetros enviados são validados, mesmo os que o processamento escolhido não usa.

### Como cada processamento aparece na prática

| Exemplo enviado | O que se percebe ouvindo | O que muda nos metadados |
|---|---|---|
| `volume` com `loudness_target=-14` | áudio mais alto e uniforme, sem estourar | `processing_params = {filter: loudnorm, target_lufs: -14, true_peak_db: -1.5, loudness_range: 11}` |
| `mono` | mesma duração, som sem separação entre canais | `channels` do processado = 1 |
| `speed` com `speed_factor=1.5` | toca 1,5x mais rápido **sem** voz fina | duração do processado menor; `speed_factor: 1.5` |
| `bitrate` com `64k` | leve perda de qualidade em agudos | `audio_bitrate: "64k"`; WAV/FLAC de entrada viram MP3 |
| `format` com `ogg` | idêntico ao original | `processed_ext = "ogg"`, MIME do OGG nas rotas de reprodução |

---

## Prints da interface

### Diálogo de conexão com o servidor

Solicitação do endereço (IP/porta) antes de abrir a janela e validação via `GET /health`.

![Diálogo de conexão com o servidor](.github/media/janela_dialogo.png)

### Janela principal

Seções de **Arquivo**, **Processamento**, **Reprodução** e **Histórico** em uma única tela.

![Janela principal do cliente](.github/media/janela_principal.png)

---

## Prints da organização dos arquivos

### Estrutura do projeto

```
Trabalho03-SD/
├── README.md
├── LICENSE                          # Mozilla Public License 2.0
├── docker-compose.yml               # servidor + PostgreSQL
├── .github/
│   └── media/                       # prints da interface e vídeo demonstrativo
├── database/
│   └── init.sql                     # schema inicial (tabela audios + índices)
│
├── client/                          # ── Cliente desktop (PySide6) ──────────
│   ├── requirements.txt             # PySide6
│   └── app/
│       ├── main.py                  # endereço do servidor + /health + MainWindow
│       ├── services/
│       │   └── audio_api.py         # HTTP: upload (multipart), histórico e imagens
│       └── views/
│           ├── main_window.py       # janela principal e orquestração
│           ├── file_selector.py     # seleção do arquivo (formato/tamanho/duração)
│           ├── processing_selector.py  # tipo de processamento e parâmetros
│           ├── playback_selector.py # players do original e do processado
│           ├── waveform.py          # forma de onda + indicador de posição
│           └── history_selector.py  # tabela do histórico
│
└── server/                          # ── Servidor (FastAPI) ────────────────
    ├── requirements.txt
    ├── Dockerfile                   # python:3.13-slim + FFmpeg
    ├── .dockerignore
    └── src/
        ├── main.py                  # FastAPI, CORS, /health
        ├── config.py                # variáveis de ambiente
        ├── database.py              # engine, sessão e criação do schema
        ├── dependencies.py          # injeção da sessão do banco
        ├── processing.py            # tipos, formatos, padrões e limites
        ├── models/audio.py          # tabela audios (SQLAlchemy)
        ├── schemas/                 # contratos da API (Pydantic)
        ├── routes/                  # audio_routes.py e trash_routes.py
        └── services/                # upload, processamento e armazenamento
```

### Organização no servidor (storage)

Cada áudio ganha uma pasta própria, agrupada por data e nomeada com o UUID informado pela API:

```
server/storage/
└── 2026-09-17/
    └── 161660b6-b1a3-4d38-8883-6fa57a09e47f/
        ├── original/
        │   └── audio.mp3           # arquivo enviado, sem alteração
        ├── processed/
        │   └── audio.mp3           # resultado do processamento
        ├── waveform-original.png   # forma de onda do arquivo enviado
        ├── waveform-processed.png  # forma de onda do resultado
        └── meta.json               # checksum, parâmetros aplicados e metadados

server/trash/
└── <uuid>/                         # mesmo conteúdo, quando o áudio é excluído
```

Os caminhos são gravados no banco **relativos** à raiz do storage, então mover a pasta de armazenamento não invalida os registros.

Para ver o que está no disco pelo container:

```bash
docker compose exec server find /app/storage -type f | sort
```

![Organização dos arquivos no servidor](.github/media/estrutura-storage.png)

---

## Vídeo demonstrativo

Demonstração em vídeo do fluxo completo: conexão com o servidor, envio de um áudio, processamento, comparação entre original e processado e leitura do histórico.

[▶ Assistir à demonstração](.github/media/video_demonstrativo.mp4)

---

## Licença

Este projeto é licenciado sob a [Mozilla Public License 2.0](LICENSE).

Projeto acadêmico da disciplina de Sistemas Distribuídos — UFPI.
