import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from math import ceil
from pathlib import Path

from faster_whisper import BatchedInferencePipeline, WhisperModel
from tqdm import tqdm
from faster_whisper.audio import decode_audio
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

_whisper_pipeline: BatchedInferencePipeline | None = None

# OpenAI transcription backend settings.
# Default to gpt-transcribe: OpenAI's recommended model for recorded speech and
# far more accurate than whisper-1 (19.3% vs 40.4% WER on their Common Voice
# launch benchmark) at $0.0045/min, 25% cheaper than whisper-1. IMPORTANT: like
# the gpt-4o-transcribe family it does NOT return segment timestamps, so
# timestamps are derived from chunk boundaries (chunk length = timestamp
# resolution). whisper-1 remains the only option here with per-segment
# timestamps via verbose_json. Override with WHISPER_OPENAI_MODEL — e.g.
# gpt-4o-mini-transcribe to halve the cost, or whisper-1 for real timestamps.
_OPENAI_MODEL = "gpt-transcribe"
_OPENAI_SAMPLE_RATE = 16000
# Models that return per-segment timestamps via response_format="verbose_json".
_OPENAI_SEGMENT_MODELS = {"whisper-1"}
# Chunk length. For timestamp-capable models this only bounds request size; for
# models without segment timestamps it also sets the timestamp resolution, so a
# small default is used there — 15 s, matching the local Whisper chunking — to
# keep timestamps fine-grained. Override with WHISPER_OPENAI_CHUNK_SECONDS.
# 2 min of 16 kHz mono 16-bit PCM ≈ 3.8 MB, well under the API's 25 MB limit.
_OPENAI_CHUNK_SECONDS = 120
_OPENAI_CHUNK_SECONDS_NO_TIMESTAMPS = 15
# Chunks are independent HTTP requests, so transcribe many concurrently. With
# 15 s chunks a ~100 min video is ~400 small requests, so keep this high.
# Override with WHISPER_OPENAI_CONCURRENCY; lower it if you hit 429 rate limits.
_OPENAI_CONCURRENCY = 16


def resolve_gpu_flag(gpu: bool | None) -> str | None:
    """Map a --gpu/--no-gpu CLI tri-state to a transcription backend override.

    True → "local" (on-GPU faster-whisper), False → "openai" (API), None →
    None (defer to $WHISPER_BACKEND / default). Pass the result as the *backend*
    argument to fetch_transcript / fetch_transcript_whisper, where an explicit
    value takes precedence over the env var (see _resolve_backend).
    """
    if gpu is None:
        return None
    return "local" if gpu else "openai"


def _resolve_backend(backend: str | None) -> str:
    """Pick the transcription backend.

    Precedence: explicit *backend* arg > $WHISPER_BACKEND env var > "local".
    Valid values are "local" (faster-whisper) and "openai" (OpenAI API).
    """
    resolved = (backend or os.environ.get("WHISPER_BACKEND") or "local").lower()
    if resolved not in ("local", "openai"):
        print(f"  Whisper: unknown backend '{resolved}', falling back to local", file=sys.stderr)
        return "local"
    return resolved


def _register_cuda_dll_dirs() -> None:
    """Make pip-installed NVIDIA CUDA runtime DLLs discoverable on Windows.

    The nvidia-*-cu12 wheels (cuBLAS, cuDNN) drop their DLLs under
    site-packages/nvidia/<lib>/bin but do not add that directory to the DLL
    search path, so CTranslate2 fails to load them for GPU inference with
    errors like "cublas64_12.dll is not found or cannot be loaded". Registering
    each such bin dir via os.add_dll_directory fixes this. No-op off Windows.
    """
    if sys.platform != "win32":
        return
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        return
    bin_dirs = []
    for nvidia_root in spec.submodule_search_locations:
        for entry in os.listdir(nvidia_root):
            bin_dir = os.path.join(nvidia_root, entry, "bin")
            if os.path.isdir(bin_dir) and any(f.endswith(".dll") for f in os.listdir(bin_dir)):
                bin_dirs.append(bin_dir)

    for bin_dir in bin_dirs:
        # add_dll_directory alone is not enough: CTranslate2 loads cuBLAS/cuDNN
        # with a plain LoadLibrary, which searches PATH, not the user-dir list.
        try:
            os.add_dll_directory(bin_dir)
        except OSError:
            pass
    if bin_dirs:
        os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ.get("PATH", "")


def _get_whisper_pipeline() -> BatchedInferencePipeline:
    global _whisper_pipeline
    if _whisper_pipeline is None:
        _register_cuda_dll_dirs()
        # Model size and compute type are env-overridable so the local backend
        # can be tuned to the GPU. On low-VRAM / Pascal cards (e.g. Quadro P620,
        # 4 GB, weak FP16), WHISPER_MODEL=small and WHISPER_COMPUTE_TYPE=int8
        # avoid OOM and the very slow float16 path.
        model_size = os.environ.get("WHISPER_MODEL", "medium")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "default")
        print(
            f"  Whisper: loading '{model_size}' model (compute_type={compute_type}, "
            "first call, will be cached)...",
            file=sys.stderr,
        )
        model = WhisperModel(model_size, device="auto", compute_type=compute_type)
        if model.model.device != "cuda":
            print(f"  Whisper: no CUDA available, running on {model.model.device} (this will be slow)", file=sys.stderr)
        else:
            print("  Whisper: running on CUDA", file=sys.stderr)
        _whisper_pipeline = BatchedInferencePipeline(model=model)
    return _whisper_pipeline


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def snippets_to_entries(fetched) -> list[dict]:
    return [
        {"timestamp": format_timestamp(snippet.start), "text": snippet.text}
        for snippet in fetched
    ]


def fetch_transcript_api(video_id: str, lang: str) -> tuple[list[dict], str] | None:
    """Try youtube-transcript-api: manual → generated → translate any available."""
    ytt = YouTubeTranscriptApi()

    try:
        transcript_list = ytt.list(video_id)
    except Exception:
        return None

    # 1. Manual captions in target language
    try:
        transcript = transcript_list.find_manually_created_transcript([lang])
        return snippets_to_entries(transcript.fetch()), "manual"
    except Exception:
        pass

    # 2. Auto-generated captions in target language
    try:
        transcript = transcript_list.find_generated_transcript([lang])
        return snippets_to_entries(transcript.fetch()), "auto-generated"
    except Exception:
        pass

    # 3. Any available transcript, translated to target language
    for transcript in transcript_list:
        try:
            translated = transcript.translate(lang)
            source = "translated-manual" if not transcript.is_generated else "translated-auto"
            return snippets_to_entries(translated.fetch()), source
        except Exception:
            continue

    return None


def fetch_transcript_ytdlp(video_id: str, lang: str) -> tuple[list[dict], str] | None:
    """Fallback: use yt-dlp to extract subtitles."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "json3",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None

    # Look for subtitles in requested_subtitles or automatic_captions
    subs = None
    for source in (info.get("requested_subtitles"), info.get("automatic_captions")):
        if source and lang in source:
            subs = source[lang]
            if isinstance(subs, list):
                if not subs:
                    continue
                # Pick the first json3 format, or fall back to the last entry
                subs = next((s for s in subs if s.get("ext") == "json3"), subs[-1])
            if "url" in subs:
                break
            subs = None

    if not subs:
        return None

    # Fetch the subtitle data from the URL
    try:
        with urllib.request.urlopen(subs["url"], timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    # json3 format has "events" with "segs" (segments)
    entries = []
    for event in data.get("events", []):
        start_ms = event.get("tStartMs", 0)
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(seg.get("utf8", "") for seg in segs).strip()
        if text:
            entries.append({
                "timestamp": format_timestamp(start_ms / 1000),
                "text": text,
            })
    return (entries, "yt-dlp") if entries else None


def _is_live(video_id: str) -> bool:
    """Check if a video is currently live."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("is_live", False) is True
    except Exception:
        return False


def _download_audio_live(url: str, tmpdir: str, timeout: int) -> bool:
    """Download a live stream's audio via subprocess with a timeout.

    Uses --live-from-start so yt-dlp grabs from the beginning.
    After *timeout* seconds the process is killed and whatever was
    written to disk is kept for transcription.
    """
    audio_template = os.path.join(tmpdir, "audio.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--quiet", "--no-warnings",
        "--live-from-start",
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "-o", audio_template,
        url,
    ]
    print(f"  Whisper: downloading live stream (timeout {timeout}s)...", file=sys.stderr)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  Whisper: timeout reached, stopping download...", file=sys.stderr)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return proc.returncode is None or proc.returncode == 0 or any(
        f.startswith("audio.") for f in os.listdir(tmpdir)
    )


def _download_audio(video_id: str, tmpdir: str, live_timeout: int) -> str | None:
    """Download a video's audio into *tmpdir* and return the file path.

    For live streams, downloads with --live-from-start and kills after
    *live_timeout* seconds, keeping whatever was captured.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    if _is_live(video_id):
        _download_audio_live(url, tmpdir, live_timeout)
    else:
        audio_template = os.path.join(tmpdir, "audio.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": audio_template,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            print(f"  Whisper: failed to download audio: {exc}", file=sys.stderr)
            return None

    # yt-dlp may save with any extension; find whatever it wrote
    audio_files = [f for f in os.listdir(tmpdir) if f.startswith("audio.")]
    if not audio_files:
        print(f"  Whisper: audio file not found after download", file=sys.stderr)
        return None
    return os.path.join(tmpdir, audio_files[0])


def _transcribe_local(audio_path: str, lang: str, chunk_length: int) -> list[dict] | None:
    """Transcribe *audio_path* with the local faster-whisper model."""
    try:
        pipeline = _get_whisper_pipeline()
    except Exception as exc:
        print(f"  Whisper: failed to load model: {exc}", file=sys.stderr)
        return None

    import time

    # Batch size drives GPU memory use. 16 is fine on big cards but OOMs a
    # 4 GB GPU (e.g. Quadro P620) with the medium model; WHISPER_BATCH_SIZE
    # lets low-VRAM cards dial it down (4 works comfortably on the P620).
    batch_size = int(os.environ.get("WHISPER_BATCH_SIZE", "16"))

    # GPU throttle: sleep between segments to yield the GPU so the machine stays
    # responsive (e.g. over RDP) instead of pegging it at 100%. The value is the
    # ratio of idle time to work time — 1.0 ≈ half speed / ~50% duty cycle,
    # 0 disables. Transcription is lazy, so pausing before pulling the next
    # segment defers the next GPU batch and leaves real idle gaps.
    throttle = max(0.0, float(os.environ.get("WHISPER_GPU_THROTTLE", "1.0")))

    try:
        note = f", throttle={throttle}" if throttle else ""
        print(f"  Whisper: transcribing audio (batch_size={batch_size}{note})...", file=sys.stderr)
        sampling_rate = pipeline.model.feature_extractor.sampling_rate
        audio = decode_audio(audio_path, sampling_rate=sampling_rate)
        duration = audio.shape[0] / sampling_rate
        clip_timestamps = [
            {"start": i * chunk_length, "end": min((i + 1) * chunk_length, duration)}
            for i in range(ceil(duration / chunk_length))
        ]
        segments, _ = pipeline.transcribe(
            audio_path,
            language=lang,
            clip_timestamps=clip_timestamps,
            batch_size=batch_size,
            beam_size=1,
            vad_filter=False,
        )
        entries = []
        last = time.time()
        for seg in tqdm(segments, desc="  Whisper", unit="seg", file=sys.stderr):
            entries.append({
                "timestamp": format_timestamp(seg.start),
                "text": seg.text.strip(),
            })
            if throttle:
                # Sleep in proportion to the time spent producing this segment
                # (GPU work), yielding the card for roughly that long.
                time.sleep((time.time() - last) * throttle)
                last = time.time()
        if not entries:
            print(f"  Whisper: transcription produced no segments", file=sys.stderr)
            return None
        return entries
    except Exception as exc:
        print(f"  Whisper: transcription failed: {exc}", file=sys.stderr)
        return None


def _transcribe_openai(audio_path: str, lang: str) -> list[dict] | None:
    """Transcribe *audio_path* via the OpenAI transcription API.

    Decodes to 16 kHz mono, splits into <25 MB WAV chunks, and transcribes the
    chunks concurrently, offsetting each chunk's timestamps back onto the
    original audio timeline. The model is set by WHISPER_OPENAI_MODEL
    (default _OPENAI_MODEL). Models in _OPENAI_SEGMENT_MODELS
    (e.g. whisper-1) return per-segment timestamps via verbose_json; other
    models return only text, so each chunk is stamped at its start offset and
    the chunk length becomes the timestamp resolution. Requires the
    OPENAI_API_KEY environment variable.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("  OpenAI: openai package not installed (run: uv add openai)", file=sys.stderr)
        return None

    import time
    import wave
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import numpy as np

    if not os.environ.get("OPENAI_API_KEY"):
        print("  OpenAI: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
        return None

    concurrency = max(1, int(os.environ.get("WHISPER_OPENAI_CONCURRENCY", str(_OPENAI_CONCURRENCY))))
    model = os.environ.get("WHISPER_OPENAI_MODEL", _OPENAI_MODEL)
    supports_segments = model in _OPENAI_SEGMENT_MODELS
    response_format = "verbose_json" if supports_segments else "json"
    default_chunk = _OPENAI_CHUNK_SECONDS if supports_segments else _OPENAI_CHUNK_SECONDS_NO_TIMESTAMPS
    chunk_seconds = max(1, int(os.environ.get("WHISPER_OPENAI_CHUNK_SECONDS", str(default_chunk))))

    try:
        client = OpenAI()
        print("  OpenAI: decoding audio...", file=sys.stderr)
        audio = decode_audio(audio_path, sampling_rate=_OPENAI_SAMPLE_RATE)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")

        total = pcm.shape[0]
        duration = total / _OPENAI_SAMPLE_RATE
        chunk_samples = chunk_seconds * _OPENAI_SAMPLE_RATE
        n_chunks = max(1, ceil(total / chunk_samples))

        # Describe every chunk up front; the actual work runs concurrently below.
        chunks = []
        for i in range(n_chunks):
            start = i * chunk_samples
            end = min((i + 1) * chunk_samples, total)
            if start >= end:
                break
            chunks.append({
                "i": i,
                "start": start,
                "end": end,
                "offset": start / _OPENAI_SAMPLE_RATE,
                "span": f"{format_timestamp(start / _OPENAI_SAMPLE_RATE)}–"
                        f"{format_timestamp(end / _OPENAI_SAMPLE_RATE)}",
            })

        workers = min(concurrency, len(chunks))
        ts_mode = "per-segment timestamps" if supports_segments else f"chunk-level timestamps ({chunk_seconds}s resolution)"
        print(
            f"  OpenAI: {format_timestamp(duration)} of audio → {len(chunks)} chunk(s) "
            f"of up to {chunk_seconds}s each, {workers} in parallel ({model}, {ts_mode})",
            file=sys.stderr,
        )

        def _transcribe_chunk(chunk: dict) -> tuple[int, list[dict], float]:
            """Write one chunk to a temp WAV, transcribe it, return its entries.

            Timestamps are offset back onto the original audio timeline. Runs in
            a worker thread; each chunk uses its own file so there is no sharing.
            """
            fd, chunk_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            req_start = time.time()
            try:
                with wave.open(chunk_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(_OPENAI_SAMPLE_RATE)
                    wf.writeframes(pcm[chunk["start"]:chunk["end"]].tobytes())
                with open(chunk_path, "rb") as fh:
                    resp = client.audio.transcriptions.create(
                        model=model,
                        file=fh,
                        language=lang,
                        response_format=response_format,
                    )
            finally:
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass

            segs = []
            if supports_segments:
                # verbose_json: fine-grained per-segment timestamps.
                for seg in getattr(resp, "segments", None) or []:
                    text = (seg.text or "").strip()
                    if text:
                        segs.append({
                            "timestamp": format_timestamp(seg.start + chunk["offset"]),
                            "text": text,
                        })
            else:
                # json/text: no timestamps returned — stamp the whole chunk at
                # its start offset (chunk length is the timestamp resolution).
                text = (getattr(resp, "text", "") or "").strip()
                if text:
                    segs.append({
                        "timestamp": format_timestamp(chunk["offset"]),
                        "text": text,
                    })
            return chunk["i"], segs, time.time() - req_start

        # Transcribe chunks concurrently; collect by index and reassemble in order.
        results: dict[int, list[dict]] = {}
        completed = 0
        run_start = time.time()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_chunk = {pool.submit(_transcribe_chunk, c): c for c in chunks}
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                completed += 1
                try:
                    idx, segs, req_elapsed = future.result()
                except Exception as exc:
                    print(
                        f"  OpenAI: [chunk {chunk['i'] + 1}/{len(chunks)}] {chunk['span']} "
                        f"FAILED: {exc}",
                        file=sys.stderr,
                    )
                    continue
                results[idx] = segs
                total_segs = sum(len(v) for v in results.values())
                print(
                    f"  OpenAI: [{completed}/{len(chunks)} done] chunk {idx + 1} {chunk['span']} "
                    f"in {req_elapsed:.1f}s (+{len(segs)} segments, {total_segs} total, "
                    f"{time.time() - run_start:.0f}s elapsed)",
                    file=sys.stderr,
                )

        entries: list[dict] = []
        for i in sorted(results):
            entries.extend(results[i])

        if not entries:
            print("  OpenAI: transcription produced no segments", file=sys.stderr)
            return None
        print(
            f"  OpenAI: transcription complete — {len(entries)} segments "
            f"in {time.time() - run_start:.0f}s ({workers}-way parallel)",
            file=sys.stderr,
        )
        return entries
    except Exception as exc:
        print(f"  OpenAI: transcription failed: {exc}", file=sys.stderr)
        return None


def fetch_transcript_whisper(
    video_id: str, lang: str, chunk_length: int = 15, live_timeout: int = 300,
    backend: str | None = None,
) -> tuple[list[dict], str] | None:
    """Last resort: download audio with yt-dlp and transcribe it.

    The *backend* selects the transcription engine (see _resolve_backend):
    "local" uses faster-whisper on this machine, "openai" uses the OpenAI
    transcription API (needs OPENAI_API_KEY; model per WHISPER_OPENAI_MODEL,
    default _OPENAI_MODEL). When *backend* is None the $WHISPER_BACKEND env
    var is consulted, defaulting to "local".
    """
    backend = _resolve_backend(backend)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(video_id, tmpdir, live_timeout)
        if audio_path is None:
            return None

        if backend == "openai":
            entries = _transcribe_openai(audio_path, lang)
            source = f"openai-{os.environ.get('WHISPER_OPENAI_MODEL', _OPENAI_MODEL)}"
        else:
            entries = _transcribe_local(audio_path, lang, chunk_length)
            source = "whisper"

        if not entries:
            return None
        return entries, source


def fetch_transcript(
    video_id: str, lang: str = "en", chunk_length: int = 15, backend: str | None = None,
) -> tuple[list[dict], str]:
    """Fetch transcript entries for *video_id*.

    Returns (entries, source).  Source is one of:
    "manual", "auto-generated", "translated-manual", "translated-auto",
    "yt-dlp", "whisper", or "openai-<model>" (e.g. "openai-gpt-transcribe").

    Tries in order:
    1. youtube-transcript-api (manual → generated → translate)
    2. yt-dlp subtitle extraction (manual + auto-generated)
    3. whisper audio transcription (local faster-whisper or the OpenAI
       transcription API, per *backend* / $WHISPER_BACKEND)

    Raises Exception if all methods fail.
    """
    result = fetch_transcript_api(video_id, lang)
    if result:
        return result

    print(f"  Transcript API failed, trying yt-dlp subtitles...", file=sys.stderr)
    result = fetch_transcript_ytdlp(video_id, lang)
    if result:
        return result

    print(f"  yt-dlp subtitles failed, trying Whisper transcription...", file=sys.stderr)
    result = fetch_transcript_whisper(video_id, lang, chunk_length, backend=backend)
    if result:
        return result

    raise Exception("All transcript fetching methods failed")


def fetch_transcript_file(
    media_path: str | Path, lang: str = "en", chunk_length: int = 15,
    backend: str | None = None,
) -> tuple[list[dict], str]:
    """Transcribe a local video/audio file using the existing Whisper backends."""
    path = str(media_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if _resolve_backend(backend) == "openai":
        entries = _transcribe_openai(path, lang)
        source = f"openai-{os.environ.get('WHISPER_OPENAI_MODEL', _OPENAI_MODEL)}"
    else:
        entries = _transcribe_local(path, lang, chunk_length)
        source = "whisper"
    if not entries:
        raise RuntimeError(f"Transcription failed for {path}")
    return entries, source
