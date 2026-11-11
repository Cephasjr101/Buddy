"""Voice layer: local VoiceStudio (voice clone + STT + TTS) with OpenAI fallback.
VoiceStudio: https://github.com/debpalash/VoiceStudio  (clone into VOICESTUDIO_DIR)
Runs fully local - no API keys needed once installed."""
import os
import subprocess
from pathlib import Path

VS_DIR = os.getenv("VOICESTUDIO_DIR", "")
VS_PY = os.getenv("VOICESTUDIO_PYTHON", "python")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")


def local_voice_available() -> bool:
    return bool(VS_DIR) and (Path(VS_DIR) / "pyproject.toml").exists() or bool(VS_DIR) and any(
        (Path(VS_DIR) / f).exists() for f in ("main.py", "app.py", "run.py"))


def transcribe(audio_path: str) -> str:
    """Voice note -> text. VoiceStudio STT -> OpenAI Whisper -> None."""
    if local_voice_available():
        try:
            r = subprocess.run([VS_PY, "-m", "voicestudio", "transcribe", audio_path],
                               capture_output=True, text=True, timeout=300, cwd=VS_DIR)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            c = OpenAI(api_key=OPENAI_KEY)
            with open(audio_path, "rb") as f:
                return c.audio.transcriptions.create(model="whisper-1", file=f).text
        except Exception:
            return ""
    return ""


def speak(text: str, voice_id: str = "", out_path: str = "") -> str:
    """Text -> audio file path. VoiceStudio TTS (cloned voice) -> OpenAI TTS -> ''."""
    out = out_path or os.path.join(UPLOAD_DIR, "tts.wav")
    if local_voice_available():
        try:
            args = [VS_PY, "-m", "voicestudio", "speak", text, "--out", out]
            if voice_id:
                args += ["--voice", voice_id]
            r = subprocess.run(args, capture_output=True, text=True, timeout=300, cwd=VS_DIR)
            if r.returncode == 0 and os.path.exists(out):
                return out
        except Exception:
            pass
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            c = OpenAI(api_key=OPENAI_KEY)
            with c.audio.speech.with_streaming_response.create(
                    model="tts-1", voice="nova", input=text) as r:
                r.stream_to_file(out)
            return out
        except Exception:
            return ""
    return ""


def clone_voice(sample_path: str, name: str) -> str:
    """Clone a voice from a sample. Returns voice_id or ''."""
    if not local_voice_available():
        return ""
    try:
        r = subprocess.run([VS_PY, "-m", "voicestudio", "clone", sample_path, "--name", name],
                           capture_output=True, text=True, timeout=900, cwd=VS_DIR)
        # voice id convention: last line of stdout
        if r.returncode == 0:
            return r.stdout.strip().splitlines()[-1][:60]
    except Exception:
        pass
    return ""
