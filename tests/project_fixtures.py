"""Small file-bound input fixtures for offline validator tests."""
from pathlib import Path

from media_evidence import digest


def bind_preflight(root: Path, project: dict, report: dict) -> None:
    directory = root / "input"
    directory.mkdir(exist_ok=True)
    project["inputs"] = {"srt": "input/source.srt", "audio": "input/narration.mp3"}
    for key, value in project["inputs"].items():
        path = root / value
        path.write_bytes(f"offline-{key}-fixture".encode())
    def timestamp(ms):
        seconds, millis = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"
    blocks = [f"{cue['id']}\n{timestamp(cue['start_ms'])} --> {timestamp(cue['end_ms'])}\n{cue['text']}\n"
              for cue in report["srt"]["cues"]]
    (root / project["inputs"]["srt"]).write_text("\n".join(blocks), encoding="utf-8")
    report.update(status="pass", errors=[], inputs={
        f"{key}_sha256": digest(root / value) for key, value in project["inputs"].items()
    })
