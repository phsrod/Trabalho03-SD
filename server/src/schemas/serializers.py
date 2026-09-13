# Adaptador entre o modelo ORM e o contrato da API.

from ..models.audio import Audio
from ..services import storage_service
from .audio import AudioResponse


def to_audio_response(audio: Audio) -> AudioResponse:
    processed_path = storage_service.resolve_path(audio.path_processed)

    return AudioResponse.from_model(audio, processed_size_bytes=storage_service.file_size(processed_path),)
