from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

from .project import load_project
from .voicevox import VoiceVoxClient


def synthesize_tts(project_dir: Path, base_url: str | None, speaker: int | None, force: bool) -> None:
    project = load_project(project_dir)
    resolved_base_url = base_url or project.tts_base_url
    resolved_speaker = speaker if speaker is not None else project.tts_speaker

    segments_json = project.path("script", "segments.json")
    if not segments_json.exists():
        raise FileNotFoundError(f"segments.json not found: {segments_json}")
    segments = json.loads(segments_json.read_text(encoding="utf-8"))

    out_dir = project.path("audio")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = VoiceVoxClient(base_url=resolved_base_url)

    for seg in segments:
        seg_id = seg["id"]
        seg_speaker = seg.get("speaker")
        if isinstance(seg_speaker, int):
            use_speaker = seg_speaker
        elif isinstance(seg_speaker, str) and seg_speaker.isdigit():
            use_speaker = int(seg_speaker)
        else:
            use_speaker = resolved_speaker
        txt_path = project.path(seg["text_path"])
        text = txt_path.read_text(encoding="utf-8").strip()
        wav_path = out_dir / f"{seg_id}.wav"
        if wav_path.exists() and not force:
            continue

        try:
            query = client.audio_query(text=text, speaker=use_speaker)
            wav = client.synthesis(query=query, speaker=use_speaker)
        except URLError as e:
            raise RuntimeError(
                "VOICEVOX(VOICEBOX) に接続できませんでした。"
                f" base_url={resolved_base_url} を確認し、ローカルAPIが起動している状態で再実行してください。"
            ) from e
        wav_path.write_bytes(wav)
