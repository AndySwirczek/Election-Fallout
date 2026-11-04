"""CLI for the post-election healthcare messaging report.

    .venv\\Scripts\\python scripts\\election_fallout\\run.py discover
    .venv\\Scripts\\python scripts\\election_fallout\\run.py transcribe
    .venv\\Scripts\\python scripts\\election_fallout\\run.py analyze
    .venv\\Scripts\\python scripts\\election_fallout\\run.py summarize
    .venv\\Scripts\\python scripts\\election_fallout\\run.py render
    .venv\\Scripts\\python scripts\\election_fallout\\run.py all
    .venv\\Scripts\\python scripts\\election_fallout\\run.py export <dir>   # markdown transcripts
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ef_common import COMPONENTS_DIR, DATA_PATH, DEFAULT_MODEL  # noqa: E402

app = typer.Typer(help="Build the post-election healthcare messaging report.", no_args_is_help=True)


def _bun() -> str:
    found = shutil.which("bun")
    if found:
        return found
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    for cand in (home / ".bun" / "bin" / "bun.exe", home / ".bun" / "bin" / "bun"):
        if cand.exists():
            return str(cand)
    raise typer.Exit("bun not found; install with: powershell -c \"irm bun.sh/install.ps1 | iex\"")


def _bun_run(*args: str) -> None:
    cmd = [_bun(), *args]
    typer.echo(f"$ {' '.join(cmd)}  (cwd={COMPONENTS_DIR.name})", err=True)
    subprocess.run(cmd, cwd=COMPONENTS_DIR, check=True)


@app.command()
def discover(
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model alias for triage."),
    no_refresh: bool = typer.Option(False, "--no-refresh", help="Skip YouTube searches; re-triage cached candidates."),
    retriage: bool = typer.Option(False, help="Re-run triage on every eligible candidate."),
):
    """Search for post-election speeches, triage them, and group uploads into events."""
    import discover as mod

    mod.run(model=model, refresh=not no_refresh, retriage=retriage)


@app.command()
def transcribe(
    only: str | None = typer.Option(None, help="Event key substring."),
    gpu: bool = typer.Option(None, "--gpu/--no-gpu", help="Force local (GPU) or OpenAI Whisper when captions are missing."),
    pause: float = typer.Option(30.0, help="Seconds to wait between YouTube videos (avoids the bot wall)."),
):
    """Transcribe the canonical recording for each event (captions first, Whisper fallback)."""
    import transcribe as mod

    mod.run(only=only, gpu=gpu, pause=pause)


@app.command()
def analyze(
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model alias."),
    force: bool = typer.Option(False, help="Re-analyze even if cached."),
    only: str | None = typer.Option(None, help="Event key substring."),
    reverify: bool = typer.Option(False, help="Only re-run quote verification on cached results."),
):
    """Extract healthcare statements and stated priorities from each transcript."""
    import analyze_speech as mod

    if reverify:
        mod.reverify()
        return
    mod.run(model=model, force=force, only=only)


@app.command()
def summarize(
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model alias."),
    keep_summary: bool = typer.Option(False, help="Reuse previously generated narrative text."),
):
    """Aggregate analyses into data.json and write the narrative sections."""
    import build_data as mod

    mod.run(model=model, regenerate=not keep_summary)


@app.command()
def render(
    install: bool = typer.Option(False, help="Run bun install + playwright install chromium first."),
    no_pdf: bool = typer.Option(False, help="Only write the HTML."),
):
    """Render data.json to HTML (React + Tailwind) and print it to PDF with Playwright."""
    if not DATA_PATH.exists():
        raise typer.Exit(f"{DATA_PATH} missing; run summarize first")
    if install:
        _bun_run("install")
        _bun_run("x", "playwright", "install", "chromium")
    _bun_run("run", "src/election/render.tsx", str(DATA_PATH))
    if not no_pdf:
        _bun_run("run", "src/election/pdf.ts")


@app.command(name="all")
def run_all(
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model alias."),
    no_refresh: bool = typer.Option(False, "--no-refresh", help="Skip YouTube searches."),
):
    """discover -> transcribe -> analyze -> summarize -> render."""
    discover(model=model, no_refresh=no_refresh, retriage=False)
    transcribe(only=None, gpu=None, pause=30.0)
    analyze(model=model, force=False, only=None, reverify=False)
    summarize(model=model, keep_summary=False)
    render(install=False, no_pdf=False)


@app.command()
def export(dest: Path = typer.Argument(..., help="Directory to write markdown transcripts into.")):
    """Write each event's full transcript as markdown with timestamped links (for sharing)."""
    import export_md as mod

    mod.run(dest)


if __name__ == "__main__":
    app()
