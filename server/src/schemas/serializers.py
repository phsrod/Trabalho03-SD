"""Adaptador entre o modelo ORM e o contrato da API.

Existe para manter ``schemas/audio.py`` puro: o único trabalho que exige consultar o
disco (descobrir o tamanho do arquivo processado) fica concentrado aqui.
"""

from ..models.audio import Audio
from ..services import storage_service
from .audio import AudioResponse


def to_audio_response(audio: Audio) -> AudioResponse:
    """Monta o ``AudioResponse`` de um registro, lendo o tamanho do processado do disco."""
    processed_path = storage_service.resolve_path(audio.path_processed)

    return AudioResponse.from_model(
        audio,
        processed_size_bytes=storage_service.file_size(processed_path),
    )
