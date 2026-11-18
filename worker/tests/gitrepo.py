"""테스트용 임시 git 저장소 만들기 (인터넷 없이 clone·이력 분석을 확인한다)."""

import os
import subprocess
from pathlib import Path

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], check=False, cwd=repo, env=_ENV, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


class Repo:
    def __init__(self, path: Path, branch: str = "trunk") -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        git(path, "init", "-q", "-b", branch)

    def commit(self, files: dict[str, str], message: str = "c") -> str:
        for name, text in files.items():
            f = self.path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)
        return git(self.path, "rev-parse", "HEAD")
