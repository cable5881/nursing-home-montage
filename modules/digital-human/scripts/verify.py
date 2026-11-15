"""Phonetic ASR gate, media integrity, and measured audio alignment."""
import difflib
import hashlib
import re
from pathlib import Path

from common import audio_duration, command, pcm, probe, write_json


def phonemes(text):
    from pypinyin import Style, lazy_pinyin
    text = "".join(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text)).lower()
    return lazy_pinyin(text, style=Style.NORMAL, errors=lambda x: list(x))


def compare_text(expected, recognized):
    expected_units, recognized_units = phonemes(expected), phonemes(recognized)
    changes = [{"operation": tag, "expected_phonemes": expected_units[a:b],
                "recognized_phonemes": recognized_units[c:d], "expected_range": [a, b]}
               for tag, a, b, c, d in difflib.SequenceMatcher(
                   None, expected_units, recognized_units, autojunk=False).get_opcodes() if tag != "equal"]
    return {"passed": bool(expected_units) and not changes, "differences": changes,
            "comparison": "Mandarin phonemes without tones; homophones allowed; ASR is not human listening."}


def check_audio(path, text, settings, directory):
    from faster_whisper import WhisperModel
    model = WhisperModel(settings["asr_model"], device="cpu", compute_type="int8",
                         cpu_threads=settings["cpu_threads"])
    segments, info = model.transcribe(str(path), language=settings["language"], beam_size=5, vad_filter=True)
    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    recognized = "".join(s["text"] for s in segments)
    result = {"expected_text": text, "recognized_text": recognized, "segments": segments,
              "language": info.language, "asr_model": settings["asr_model"],
              "decoded_duration_seconds": audio_duration(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              "content": compare_text(text, recognized), "human_listening_performed": False}
    result["passed"] = result["content"]["passed"] and 0 < result["decoded_duration_seconds"] < 300
    write_json(Path(directory) / "audio-check.json", result)
    return result


def alignment(video, audio):
    import numpy as np
    def samples(path):
        a = np.frombuffer(pcm(path, 8000), dtype="<i2").astype(float)
        return a - a.mean()
    source, returned = samples(audio), samples(video)
    size = 1 << (len(source) + len(returned) - 1).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(returned, size) * np.conj(np.fft.rfft(source, size)), size)
    lags = np.arange(-2400, 2401)
    lag = int(lags[np.argmax(correlation[lags % size])])
    x = source[max(0, -lag):min(len(source), len(returned) - lag)]
    y = returned[max(0, lag):min(len(returned), len(source) + lag)]
    norm = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    coefficient = float(np.dot(x, y) / norm) if norm else 0.0
    return {"lag_seconds": lag / 8000, "correlation": coefficient,
            "passed": abs(lag / 8000) <= 0.08 and coefficient >= 0.95}


def finalize(directory, state):
    directory = Path(directory)
    raw, audio = directory / "provider-video.mp4", Path(state["submitted_audio"])
    timing = alignment(raw, audio)
    write_json(directory / "alignment.json", timing)
    if not timing["passed"]:
        raise RuntimeError("接口回传音频与配音未通过对齐检查；保留原片，先核查再换轨。")
    duration = state["submitted_duration"]
    if float(next(s for s in probe(raw)["streams"] if s["codec_type"] == "video")["duration"]) + 0.05 < duration:
        raise RuntimeError("生成画面短于配音，停止导出，保留接口原片。")
    output = directory / "digital-human.mp4"
    command(["ffmpeg", "-y", "-v", "error", "-i", raw, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
             "-t", duration, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", output])
    command(["ffmpeg", "-v", "error", "-i", output, "-f", "null", "-"])
    metadata = probe(output)
    qc = directory / "qc"
    qc.mkdir(exist_ok=True)
    frames = []
    for index, position in enumerate((min(0.6, duration / 4), duration / 2, max(0, duration - 0.5))):
        image = qc / f"frame-{index}.jpg"
        command(["ffmpeg", "-y", "-v", "error", "-ss", position, "-i", output, "-frames:v", "1", image])
        frames.append(str(image))
    result = {"output": str(output), "duration_seconds": float(metadata["format"]["duration"]),
              "streams": [{k: s.get(k) for k in ("codec_type", "codec_name", "width", "height", "duration")}
                          for s in metadata["streams"]], "alignment": timing, "complete_decode": True,
              "visual_review_frames": frames, "visual_review_pending": True,
              "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    write_json(directory / "verification.json", result)
    return result
