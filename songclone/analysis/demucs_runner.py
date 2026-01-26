"""Stem separation using Demucs."""

import asyncio
import logging
import os
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class StemPaths(NamedTuple):
    """Paths to separated stem files."""

    vocals: Path
    drums: Path
    bass: Path
    other: Path


async def separate_stems(
    audio_path: Path,
    output_dir: Path,
    model: str = "htdemucs",
) -> StemPaths:
    """
    Separate audio into stems using Demucs.

    Args:
        audio_path: Path to input audio file (WAV or MP3)
        output_dir: Directory to write separated stems
        model: Demucs model to use (default: htdemucs for best quality)

    Returns:
        StemPaths with paths to vocals, drums, bass, other stems
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting stem separation for {audio_path}")

    try:
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
        from demucs.audio import save_audio
        import torch
        import torchaudio

        demucs_model = get_model(model)
        demucs_model.eval()

        wav, sr = torchaudio.load(str(audio_path))

        if wav.dim() == 1:
            wav = wav.unsqueeze(0)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)

        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()

        with torch.no_grad():
            sources = apply_model(
                demucs_model,
                wav[None],
                device="cuda" if torch.cuda.is_available() else "cpu",
                progress=True,
            )[0]

        sources = sources * ref.std() + ref.mean()

        stem_names = demucs_model.sources
        stem_paths = {}

        for i, stem_name in enumerate(stem_names):
            stem_path = output_dir / f"{stem_name}.wav"
            save_audio(sources[i], str(stem_path), sr)
            stem_paths[stem_name] = stem_path
            logger.info(f"Saved {stem_name} stem to {stem_path}")

        return StemPaths(
            vocals=stem_paths.get("vocals", output_dir / "vocals.wav"),
            drums=stem_paths.get("drums", output_dir / "drums.wav"),
            bass=stem_paths.get("bass", output_dir / "bass.wav"),
            other=stem_paths.get("other", output_dir / "other.wav"),
        )

    except ImportError:
        logger.warning("Demucs not available, using fallback (copying original)")
        return await _fallback_separation(audio_path, output_dir)


async def _fallback_separation(audio_path: Path, output_dir: Path) -> StemPaths:
    """Fallback when Demucs is not available - just copy the original as 'other'."""
    import shutil

    stems = ["vocals", "drums", "bass", "other"]
    paths = {}

    for stem in stems:
        stem_path = output_dir / f"{stem}.wav"
        if stem == "other":
            shutil.copy(audio_path, stem_path)
        else:
            stem_path.touch()
        paths[stem] = stem_path

    return StemPaths(
        vocals=paths["vocals"],
        drums=paths["drums"],
        bass=paths["bass"],
        other=paths["other"],
    )
