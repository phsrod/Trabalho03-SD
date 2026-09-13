import json
import subprocess
from pathlib import Path


def get_audio_metadata(file_path: Path):
    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    data = json.loads(result.stdout)

    audio_stream = None

    for stream in data["streams"]:
        if stream["codec_type"] == "audio":
            audio_stream = stream
            break

    metadata = {
        "duration_sec": float(data["format"].get("duration", 0)),
        "sample_rate": int(audio_stream.get("sample_rate", 0)),
        "channels": int(audio_stream.get("channels", 0)),
        "bitrate": int(data["format"].get("bit_rate", 0))
    }

    return metadata