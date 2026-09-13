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

def process_audio(input_path: Path, output_path: Path, processing_type: str):
    if processing_type == "volume":
        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-filter:a", "volume=2.0",
            str(output_path)
        ]

    elif processing_type == "mono":
        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-ac", "1",
            str(output_path)
        ]

    elif processing_type == "speed":
        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-filter:a", "atempo=1.5",
            str(output_path)
        ]

    elif processing_type == "bitrate":
        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-b:a", "64k",
            str(output_path)
        ]

    elif processing_type == "format":
        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            str(output_path)
        ]

    else:
        raise ValueError("Tipo de processamento inválido")

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    return output_path

def create_metadata_file(
    directory: Path,
    audio_id,
    original_name,
    size_bytes,
    metadata,
    processing_type
):
    data = {
        "id": str(audio_id),
        "original_name": original_name,
        "size_bytes": size_bytes,
        "duration_sec": metadata["duration_sec"],
        "sample_rate": metadata["sample_rate"],
        "channels": metadata["channels"],
        "bitrate": metadata["bitrate"],
        "processing_type": processing_type
    }

    metadata_path = directory / "meta.json"

    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        json.dump(
            data,
            metadata_file,
            indent=4,
            ensure_ascii=False
        )

    return metadata_path

def create_waveform(file_path: Path, output_path: Path):
    command = [
        "ffmpeg",
        "-y",
        "-i", str(file_path),
        "-filter_complex", "showwavespic=s=1200x400",
        "-frames:v", "1",
        str(output_path)
    ]

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    return output_path