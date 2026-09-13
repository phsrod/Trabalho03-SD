# Referência da API - Servidor de Processamento de Áudio

Base URL (servidor local): `http://localhost:8000`
Base URL (da outra máquina): `http://<ip-do-servidor>:8000`

> Descubra o IP do servidor com `ipconfig` (Windows) ou `hostname -I` (Linux).
> A documentação interativa fica em `/docs` e o schema em `/openapi.json`.

---

## Convenções

1. **Todas as respostas são JSON**, exceto as rotas que devolvem arquivo (`/original`, `/processed`,
   `/waveform`, `/download/...`), que devolvem o binário do arquivo.
2. **As URLs da resposta são relativas** (`/audios/<uuid>/original`). O cliente deve concatenar com a
   base URL: `f"{base_url}{audio['original_url']}"`.
3. **Envio de arquivo** é sempre `multipart/form-data` com o campo `file`.
4. **UUIDs inválidos** retornam `422`; UUIDs válidos porém inexistentes retornam `404`;
   áudios na lixeira retornam `410`.
5. Erros seguem o formato `{"detail": "mensagem em português"}` (ou a lista de erros do FastAPI no `422`).
6. Os campos `duration_sec`, `sample_rate`, `channels`, `bitrate` e `size_bytes` referem-se ao
   **arquivo original**. Os dados do arquivo processado aparecem em `processed_ext`,
   `processed_size_bytes` e no `meta.json`.
7. Todas as rotas de listagem e de streaming aceitam requisições de qualquer origem (CORS liberado).

---

## Objeto `AudioResponse`

Toda rota que devolve áudio usa este formato:

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string (UUID) | Identificador único do áudio |
| `original_name` | string | Nome do arquivo enviado (ex.: `musica.mp3`) |
| `original_ext` | string | Extensão sem ponto (`mp3`) |
| `mime_type` | string | MIME do original (`audio/mpeg`) |
| `size_bytes` | int | Tamanho do original em bytes |
| `duration_sec` | float | Duração em segundos |
| `sample_rate` | int | Taxa de amostragem em Hz |
| `channels` | int | Número de canais |
| `bitrate` | int | Taxa de bits em bps |
| `processing_type` | string | `original`, `volume`, `mono`, `speed`, `bitrate` ou `format` |
| `processing_params` | objeto | Parâmetros realmente aplicados (ex.: `{"speed_factor": 1.75}`) |
| `checksum` | string | SHA-256 do arquivo original |
| `created_at` | string | Data/hora do envio (`2026-09-13T15:22:36.761783`) |
| `deleted_at` | string ou null | Preenchido quando está na lixeira |
| `is_deleted` | bool | `true` se está na lixeira |
| `path_original` | string | Caminho no servidor (informativo) |
| `path_processed` | string | Caminho no servidor (informativo) |
| `processed_ext` | string | Extensão do arquivo processado |
| `processed_size_bytes` | int | Tamanho do arquivo processado |
| `original_url` | string | URL do áudio original (para tocar/baixar) |
| `processed_url` | string | URL do áudio processado |
| `waveform_url` | string | URL da imagem `waveform.png` |
| `metadata_url` | string | URL do `meta.json` |

Exemplo completo:

```json
{
  "id": "b1ea98de-9c44-4338-8373-6162c00dccab",
  "original_name": "teste.wav",
  "original_ext": "wav",
  "mime_type": "audio/wav",
  "size_bytes": 529244,
  "duration_sec": 3.0,
  "sample_rate": 44100,
  "channels": 2,
  "bitrate": 1411317,
  "processing_type": "volume",
  "processing_params": { "filter": "loudnorm", "target_lufs": -14.0, "true_peak_db": -1.5, "loudness_range": 11 },
  "checksum": "768ec91faf910a02f61320331189e9f61a31a7a40bd700b0cbb8a63283c1038a",
  "created_at": "2026-09-13T15:22:36.761783",
  "deleted_at": null,
  "is_deleted": false,
  "path_original": "/app/storage/2026-09-13/b1ea98de-.../original/audio.wav",
  "path_processed": "/app/storage/2026-09-13/b1ea98de-.../processed/audio.wav",
  "processed_ext": "wav",
  "processed_size_bytes": 529278,
  "original_url": "/audios/b1ea98de-.../original",
  "processed_url": "/audios/b1ea98de-.../processed",
  "waveform_url": "/audios/b1ea98de-.../waveform",
  "metadata_url": "/audios/b1ea98de-.../meta"
}
```

---

## 1. Enviar áudio

```
POST /audios/upload
Content-Type: multipart/form-data
```

| Campo | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `file` | arquivo | **sim** | — | Arquivo de áudio (`wav, mp3, ogg, oga, flac, m4a, aac, opus, wma, aiff, aif, webm`) |
| `processing_type` | string | não | `original` | Processamento a aplicar |
| `loudness_target` | float | não | `-16.0` | Alvo em LUFS (de -40 a 0), usado com `volume` |
| `speed_factor` | float | não | `1.5` | Velocidade (de 0.5 a 2.0), usado com `speed` |
| `bitrate` | string | não | `64k` | Taxa de bits no formato `<kbps>k`, usada com `bitrate` |
| `target_format` | string | não | `wav` | `wav, mp3, ogg, flac, m4a, opus`, usado com `format` |

Só os parâmetros do processamento escolhido são usados; os outros são ignorados.

**Resposta `201 Created`**: um objeto `AudioResponse`.

```bash
curl -F "file=@musica.mp3" \
     -F "processing_type=volume" \
     -F "loudness_target=-14" \
     http://localhost:8000/audios/upload
```

O que o servidor faz em ordem:

1. Valida a extensão e gera um **UUID**.
2. Grava `storage/<data>/<uuid>/original/audio.<ext>`.
3. Lê os metadados com o `ffprobe` (se não houver faixa de áudio, responde `400`).
4. Gera `storage/<data>/<uuid>/processed/audio.<ext>` com o processamento pedido.
5. Gera `waveform.png` e o `meta.json`.
6. Insere a linha na tabela `audios` do PostgreSQL.
7. Se qualquer etapa falhar, a pasta do UUID é apagada (nada de lixo no storage).

Extensão do arquivo processado conforme o processamento:

| Processamento | Extensão do processado |
|---|---|
| `original`, `volume`, `mono`, `speed` | a mesma do original |
| `bitrate` (fonte com perda: mp3/ogg/m4a/aac/opus/wma) | a mesma do original |
| `bitrate` (fonte sem perda: wav/flac/aiff, onde reduzir bitrate não faz sentido) | `mp3` |
| `format` | o `target_format` enviado |

## 2. Tipos de processamento

```
GET /audios/processing-types
```

Ideal para preencher o combo box do cliente sem chumbar valores:

```json
[
  { "key": "original", "label": "Sem processamento", "description": "Mantém o áudio original...", "parameters": {} },
  { "key": "volume", "label": "Normalização de volume", "description": "Normaliza o volume usando o filtro loudnorm (padrão EBU R128).", "parameters": { "loudness_target": -16.0 } },
  { "key": "mono", "label": "Conversão para mono", "description": "Converte o áudio para um único canal.", "parameters": {} },
  { "key": "speed", "label": "Alteração de velocidade", "description": "Altera a velocidade de reprodução sem mudar o tom (filtro atempo).", "parameters": { "speed_factor": 1.5 } },
  { "key": "bitrate", "label": "Redução da taxa de bits", "description": "Recomprime o áudio com uma taxa de bits menor (em formatos com perda).", "parameters": { "bitrate": "64k" } },
  { "key": "format", "label": "Conversão de formato", "description": "Converte o áudio para outro formato/container.", "parameters": { "target_format": "wav" } }
]
```

## 3. Histórico

```
GET /audios/
```

| Query string | Padrão | Descrição |
|---|---|---|
| `processing_type` | — | Filtra por processamento (`volume`, `mono`, ...) |
| `search` | — | Busca parcial pelo nome original |
| `include_deleted` | `false` | Inclui os áudios que estão na lixeira |
| `skip` | `0` | Paginação (quantos pular) |
| `limit` | `100` | Máximo de itens (1 a 500) |

Retorna uma **lista** de `AudioResponse`, do mais recente para o mais antigo.

```bash
curl "http://localhost:8000/audios/?processing_type=mono&search=musica"
```

⚠️ A rota tem barra no final (`/audios/`). Requisições para `/audios` são redirecionadas (307).

## 4. Detalhe de um áudio

```
GET /audios/{id}                          -> AudioResponse
GET /audios/{id}/files                    -> lista dos arquivos em disco
GET /audios/{id}/meta                     -> conteúdo do meta.json
```

`/audios/{id}/files`:

```json
[
  { "name": "meta.json", "relative_path": "meta.json", "size_bytes": 1387 },
  { "name": "audio.wav", "relative_path": "original/audio.wav", "size_bytes": 529244 },
  { "name": "audio.wav", "relative_path": "processed/audio.wav", "size_bytes": 529278 },
  { "name": "waveform.png", "relative_path": "waveform.png", "size_bytes": 3577 }
]
```

## 5. Reprodução e download

```
GET /audios/{id}/original              -> arquivo original  (Content-Type pelo formato)
GET /audios/{id}/processed             -> arquivo processado
GET /audios/{id}/waveform              -> image/png
GET /audios/{id}/download/original     -> download (Content-Disposition: attachment)
GET /audios/{id}/download/processed    -> download
```

As rotas de áudio **suportam `Range`** (`Accept-Ranges: bytes`), ou seja, o player consegue
avançar/retroceder e o servidor responde `206 Partial Content`:

```
HTTP/1.1 200 OK
content-type: audio/wav
content-length: 529244
accept-ranges: bytes
content-disposition: inline; filename="original.wav"
```

> Para tocar no cliente, prefira baixar o arquivo para uma pasta temporária e passar o caminho
> local para o `QMediaPlayer` (ver `docs/GUIA_CLIENTE.md`). Assim o player tem o arquivo completo
> e o *seek* funciona sem depender de streaming HTTP.

## 6. Excluir (mover para a lixeira)

```
DELETE /audios/{id}
```

```json
{ "message": "Áudio movido para a lixeira. Use POST /trash/{id}/restore para restaurar.", "id": "b1ea98de-..." }
```

A pasta vai para `trash/<uuid>` e o campo `deleted_at` é preenchido. O áudio desaparece do `GET /audios/`
e as rotas de reprodução passam a responder `410 Gone`:

```json
{ "detail": "Este áudio está na lixeira. Use POST /trash/{id}/restore para restaurá-lo." }
```

## 7. Lixeira

```
GET    /trash/                  -> lista os itens da lixeira
POST   /trash/{id}/restore      -> restaura (volta para storage/<data>/<uuid>)
DELETE /trash/{id}              -> exclui definitivamente (apaga do disco e do banco)
DELETE /trash/                  -> esvazia a lixeira
```

`GET /trash/`:

```json
[
  {
    "id": "b1ea98de-...",
    "directory": "/app/trash/b1ea98de-...",
    "size_bytes": 1067446,
    "files": ["meta.json", "original/audio.wav", "processed/audio.wav", "waveform.png"],
    "deleted_at": "2026-09-13T15:23:25.924698",
    "audio": { "...": "objeto AudioResponse (ou null se o registro não existir mais)" }
  }
]
```

`DELETE /trash/`:

```json
{ "message": "Lixeira esvaziada.", "removed_directories": 3, "removed_records": 3 }
```

## 8. Infraestrutura

```
GET /          -> resumo com os principais endpoints
GET /health    -> { "status": "ok", "database": "ok", "storage_path": "/app/storage", "trash_path": "/app/trash" }
GET /web       -> interface web (players + waveform + lixeira, no navegador)
GET /docs      -> Swagger UI
```

O cliente pode usar `/health` na inicialização para avisar quando o servidor estiver fora do ar.

---

## Códigos de erro

| Código | Quando acontece | Exemplo de `detail` |
|---|---|---|
| `400` | Extensão não suportada, arquivo vazio, sem faixa de áudio, parâmetro inválido | `"Formato '.txt' não suportado. Aceitos: wav, mp3, ..."` |
| `404` | UUID inexistente, arquivo/registro não encontrado | `"Áudio não encontrado."` |
| `410` | O áudio está na lixeira | `"Este áudio está na lixeira. Use POST /trash/{id}/restore..."` |
| `413` | Arquivo maior que o limite (200 MB por padrão) | `"O arquivo excede o limite de 200 MB."` |
| `409` | Restaurar um áudio que não está na lixeira / pasta já existente | `"Este áudio não está na lixeira."` |
| `422` | Validação do FastAPI (UUID inválido, `processing_type` desconhecido) | `[{"loc": ["body", "processing_type"], "msg": "Input should be 'original', 'volume', ..."}]` |
| `500` | Falha do FFmpeg ou erro inesperado | `"Falha no processamento: FFmpeg falhou: ..."` |

---

## Roteiro de demonstração (sugestão)

1. `docker compose up --build -d` e abra `http://localhost:8000/docs`.
2. No cliente, escolha um arquivo e o processamento **Normalização de volume**; mostre a duração, o
   formato e o tamanho lidos localmente.
3. Envie e mostre o `id` (UUID) e o `processing_params` retornados.
4. Reproduza o **original** e o **processado** no cliente e compare.
5. Abra `http://localhost:8000/web` e mostre a lista, os dois players e a `waveform.png`.
6. Mostre o histórico (`GET /audios/`) e o `meta.json` (`GET /audios/{id}/meta`).
7. Mostre a organização no disco:
   `docker compose exec server find /app/storage -type f | sort`.
8. Mostre o banco:
   `docker compose exec postgres psql -U postgres -d audio_db -c "SELECT original_name, processing_type, duration_sec, checksum, path_processed FROM audios ORDER BY created_at DESC;"`
9. Teste a lixeira: exclua um áudio, mostre `trash/`, restaure e mostre que voltou a tocar.
