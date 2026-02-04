from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavInfo:
    nchannels: int
    sampwidth: int
    framerate: int
    nframes: int

    @property
    def duration_sec(self) -> float:
        if self.framerate <= 0:
            return 0.0
        return self.nframes / float(self.framerate)


def read_wav_info(path: Path) -> WavInfo:
    with wave.open(str(path), "rb") as wf:
        return WavInfo(
            nchannels=wf.getnchannels(),
            sampwidth=wf.getsampwidth(),
            framerate=wf.getframerate(),
            nframes=wf.getnframes(),
        )


def concat_wavs(in_paths: list[Path], out_path: Path) -> WavInfo:
    if not in_paths:
        raise ValueError("in_paths is empty")

    infos = [read_wav_info(p) for p in in_paths]
    first = infos[0]
    for p, info in zip(in_paths, infos, strict=True):
        if (info.nchannels, info.sampwidth, info.framerate) != (
            first.nchannels,
            first.sampwidth,
            first.framerate,
        ):
            raise ValueError(
                "WAV parameters mismatch; cannot concat safely. "
                f"first={first.nchannels}/{first.sampwidth}/{first.framerate}, "
                f"got={p.name}:{info.nchannels}/{info.sampwidth}/{info.framerate}"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out_wf:
        out_wf.setnchannels(first.nchannels)
        out_wf.setsampwidth(first.sampwidth)
        out_wf.setframerate(first.framerate)
        total_frames = 0
        for p in in_paths:
            with wave.open(str(p), "rb") as in_wf:
                frames = in_wf.readframes(in_wf.getnframes())
                out_wf.writeframes(frames)
                total_frames += in_wf.getnframes()

    return WavInfo(
        nchannels=first.nchannels,
        sampwidth=first.sampwidth,
        framerate=first.framerate,
        nframes=total_frames,
    )

