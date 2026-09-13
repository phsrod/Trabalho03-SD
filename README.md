# Trabalho 03 - Sistemas Distribuídos

Sistema cliente/servidor em **três camadas** para enviar, processar e armazenar arquivos de áudio.

```
┌─────────────────────────┐        HTTP (multipart/JSON)        ┌─────────────────────────┐
│  Cliente (PySide6)      │ ──────────────────────────────────► │  Servidor (FastAPI)     │
│  - escolhe o arquivo    │ ◄────────────────────────────────── │  - recebe e processa    │
│  - escolhe o áudio      │        áudio / metadados / JSON     │    com FFmpeg           │
│  - reproduz e vê o      │                                     │  - organiza em disco    │
│    histórico            │                                     │  - interface web em /web│
└─────────────────────────┘                                     └────────────┬────────────┘
                                                                             │ SQLAlchemy
                                                                             ▼
                                                                ┌────────────────────────┐
                                                                │  PostgreSQL (audios)   │
                                                                └────────────────────────┘
```

> **Parte do cliente:** veja [`docs/GUIA_CLIENTE.md`](docs/GUIA_CLIENTE.md).
> **Referência da API:** veja [`docs/API.md`](docs/API.md) (ou `http://<ip-do-servidor>:8000/docs`).

---

## Tecnologias

| Camada | Tecnologias |
|---|---|
| Cliente | Python 3, PySide6 |
| Servidor | Python 3, FastAPI, Uvicorn, FFmpeg (`ffmpeg` + `ffprobe`) |
| Banco | PostgreSQL 17, SQLAlchemy |

---

## Como executar o servidor

Precisa apenas do **Docker** (o FFmpeg e o PostgreSQL sobem junto):

```bash
docker compose up --build -d
```

Serviços expostos:

| Serviço | URL |
|---|---|
| API | http://localhost:8000 |
| Documentação interativa (Swagger) | http://localhost:8000/docs |
| Interface web dos áudios | http://localhost:8000/web |
| Estado do servidor | http://localhost:8000/health |
| PostgreSQL | localhost:5432 (usuário `postgres`, senha `postgres`, banco `audio_db`) |

Comandos úteis:

```bash
docker compose logs -f server        # acompanhar os logs
docker compose down                  # parar (mantém os dados)
docker compose down -v               # parar e apagar o banco (recria as tabelas)
```

### Rodando sem Docker (opcional, para depurar)

```bash
cd server
pip install -r requirements.txt
# o FFmpeg precisa estar instalado no sistema e o PostgreSQL acessível
set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/audio_db
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Sem Docker as pastas usadas são `server/storage` e `server/trash`.

---

## Teste rápido

```bash
# envia um áudio aplicando normalização de volume (-14 LUFS)
curl -F "file=@musica.mp3" -F "processing_type=volume" -F "loudness_target=-14" \
     http://localhost:8000/audios/upload

# histórico
curl http://localhost:8000/audios/

# tipos de processamento disponíveis
curl http://localhost:8000/audios/processing-types
```

---

## Processamentos disponíveis

| `processing_type` | O que faz | Parâmetro opcional (padrão) |
|---|---|---|
| `original` | Não altera o áudio (grava uma cópia idêntica) | — |
| `volume` | Normalização de volume (filtro `loudnorm`, padrão EBU R128) | `loudness_target` (`-16.0` LUFS) |
| `mono` | Converte para um único canal | — |
| `speed` | Altera a velocidade sem mudar o tom (filtro `atempo`) | `speed_factor` (`1.5`, de 0.5 a 2.0) |
| `bitrate` | Reduz a taxa de bits | `bitrate` (`64k`) |
| `format` | Converte o formato do arquivo | `target_format` (`wav`, `mp3`, `ogg`, `flac`, `m4a`, `opus`) |

Formatos aceitos no upload: `wav, mp3, ogg, oga, flac, m4a, aac, opus, wma, aiff, aif, webm` (limite de 200 MB).

---

## Regras de armazenamento

Cada áudio recebe um **UUID único** e todos os arquivos de áudio são gravados sempre com o nome `audio.<ext>`,
dentro de uma pasta organizada por data:

```
server/storage/2026-09-13/b1ea98de-9c44-4338-8373-6162c00dccab/
├── original/audio.wav      # arquivo enviado pelo cliente (nome sempre audio.<ext>)
├── processed/audio.wav     # resultado do processamento (idem)
├── waveform.png            # forma de onda gerada automaticamente
└── meta.json               # checksum, parâmetros usados, tamanhos e metadados

server/trash/<uuid>/...     # áudios marcados para exclusão ficam aqui
```

O `meta.json` guarda as informações complementares pedidas no trabalho:

```json
{
  "id": "b1ea98de-...",
  "original_name": "musica.mp3",
  "processing_type": "volume",
  "processing_params": { "filter": "loudnorm", "target_lufs": -14.0, "true_peak_db": -1.5, "loudness_range": 11 },
  "checksum_sha256": "768ec91f...",
  "storage": {
    "directory": "2026-09-13/<uuid>",
    "original": "2026-09-13/<uuid>/original/audio.mp3",
    "processed": "2026-09-13/<uuid>/processed/audio.mp3",
    "waveform": "waveform.png",
    "metadata": "meta.json"
  },
  "original": { "file": "2026-09-13/<uuid>/original/audio.mp3", "size_bytes": 733645, "duration_sec": 42.06, "sample_rate": 44100, "channels": 2, "bitrate": 128000 },
  "processed": { "file": "2026-09-13/<uuid>/processed/audio.mp3", "size_bytes": 449237, "duration_sec": 42.06, "sample_rate": 44100, "channels": 2, "bitrate": 128000 }
}
```

Os caminhos gravados no banco (`path_original` / `path_processed`) e no `meta.json`
são **relativos à raiz do storage**, então mudar a pasta de armazenamento (ou rodar em
outra máquina) não invalida os registros. O servidor resolve o caminho absoluto na
hora de servir o arquivo.

A exclusão é **reversível**: `DELETE /audios/{id}` move a pasta para `trash/<uuid>` e marca `deleted_at`
no banco. Para desfazer existe `POST /trash/{id}/restore`; para apagar de verdade existem
`DELETE /trash/{id}` e `DELETE /trash/` (esvaziar).

---

## Banco de dados (tabela `audios`)

| Campo | Tipo | Observação |
|---|---|---|
| `id` | UUID | chave primária |
| `original_name` | VARCHAR(255) | nome do arquivo enviado |
| `original_ext` | VARCHAR(20) | extensão do arquivo enviado |
| `mime_type` | VARCHAR(100) | ex.: `audio/mpeg` |
| `size_bytes` | BIGINT | tamanho do arquivo original |
| `duration_sec` | DOUBLE PRECISION | duração em segundos |
| `sample_rate` | INTEGER | taxa de amostragem (Hz) |
| `channels` | INTEGER | quantidade de canais |
| `bitrate` | INTEGER | taxa de bits (bps) |
| `processing_type` | VARCHAR(50) | processamento aplicado |
| `processing_params` | JSONB | parâmetros usados no processamento |
| `checksum` | VARCHAR(64) | SHA-256 do arquivo original |
| `created_at` | TIMESTAMP | data do envio |
| `deleted_at` | TIMESTAMP | preenchido quando o áudio vai para a lixeira |
| `path_original` | TEXT | caminho do arquivo original |
| `path_processed` | TEXT | caminho do arquivo processado |

`duration_sec`, `sample_rate`, `channels`, `bitrate` e `size_bytes` descrevem o **arquivo original** enviado
pelo cliente (é o que o cliente mostra na tela de informações básicas). Os dados do arquivo processado ficam
no `meta.json` (seção `processed`) e também em `processed_ext` / `processed_size_bytes` na resposta da API.

Consultar pelo terminal:

```bash
docker compose exec postgres psql -U postgres -d audio_db -c "SELECT original_name, processing_type, duration_sec, checksum FROM audios;"
```

---

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST | `/audios/upload` | Envia o áudio e aplica o processamento |
| GET | `/audios/` | Histórico (filtros: `processing_type`, `search`, `include_deleted`, `skip`, `limit`) |
| GET | `/audios/processing-types` | Processamentos disponíveis (com parâmetros padrão) |
| GET | `/audios/{id}` | Metadados de um áudio |
| GET | `/audios/{id}/original` | Áudio original (suporta `Range` para o player) |
| GET | `/audios/{id}/processed` | Áudio processado |
| GET | `/audios/{id}/waveform` | Imagem `waveform.png` |
| GET | `/audios/{id}/meta` | Conteúdo do `meta.json` |
| GET | `/audios/{id}/files` | Arquivos em disco daquele áudio |
| GET | `/audios/{id}/download/original` | Download do original |
| GET | `/audios/{id}/download/processed` | Download do processado |
| DELETE | `/audios/{id}` | Move para a lixeira |
| GET | `/trash/` | Lista a lixeira |
| POST | `/trash/{id}/restore` | Restaura um áudio |
| DELETE | `/trash/{id}` | Exclui definitivamente |
| DELETE | `/trash/` | Esvazia a lixeira |
| GET | `/health` | Estado do servidor e do banco |
| GET | `/web` | Interface web para ouvir os áudios |

Detalhes de requisição/resposta, códigos de erro e exemplos: [`docs/API.md`](docs/API.md).

---

## Estrutura do repositório

```
.
├── client/                  # camada cliente (PySide6) - responsabilidade da dupla
│   └── app/main.py
├── server/
│   ├── Dockerfile
│   ├── requirements.txt         # dependências (versões fixadas)
│   ├── src/
│   │   ├── main.py              # aplicação FastAPI, CORS, /health, /web
│   │   ├── config.py            # caminhos e variáveis de ambiente
│   │   ├── processing.py        # domínio: tipos, limites e catálogo de processamentos
│   │   ├── database.py          # engine, sessão, criação/migração das tabelas
│   │   ├── dependencies.py      # dependência get_db
│   │   ├── models/audio.py      # modelo ORM da tabela audios
│   │   ├── schemas/
│   │   │   ├── audio.py         # contratos da API (puros, sem I/O)
│   │   │   └── serializers.py   # modelo -> contrato da API
│   │   ├── routes/
│   │   │   ├── audio_routes.py  # upload, histórico, streaming, exclusão
│   │   │   └── trash_routes.py  # lixeira (listar, restaurar, esvaziar)
│   │   ├── services/
│   │   │   ├── upload_service.py   # pipeline do upload (orquestração)
│   │   │   ├── audio_service.py    # FFmpeg/FFprobe (processamento e waveform)
│   │   │   └── storage_service.py  # pastas, meta.json, checksum, lixeira
│   │   └── web/index.html       # interface web do servidor
│   ├── storage/                 # áudios armazenados  (ignorado no git)
│   └── trash/                   # lixeira             (ignorado no git)
├── database/init.sql            # criação da tabela audios
└── docker-compose.yml           # servidor + PostgreSQL
```

### Organização em camadas

```
rotas (HTTP)  ->  services (regras de negócio)  ->  models / banco
     |                    |
     v                    v
 schemas (contratos)  processing (domínio puro) + FFmpeg + disco
```

- As **rotas** não contêm regra de negócio: validam a entrada, chamam o serviço e
traduzem exceções de domínio em status HTTP.
- Os **serviços** não conhecem HTTP (nenhum `HTTPException` fora das rotas).
- Os **schemas** são puros (não acessam banco nem disco); a conversão de modelo para
resposta fica em `schemas/serializers.py`.
- As **regras de domínio** (limites dos parâmetros, catálogo de processamentos) ficam em
`processing.py`, usado tanto pela validação da API quanto pelos serviços, sem duplicação.

### Migração do banco

O `init.sql` só roda quando o volume do PostgreSQL é criado. Para bancos já existentes,
`init_db()` compara o modelo ORM com a tabela e adiciona automaticamente as colunas que
faltam (ver `_add_missing_columns` em `server/src/database.py`), de forma idempotente.
Em um projeto maior o caminho seria usar Alembic.
