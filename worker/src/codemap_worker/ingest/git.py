"""git 실행 도우미. 저장소는 남의 코드이므로 모든 git 호출을 여기로 모아 안전하게 실행한다.

- 셸을 쓰지 않고 인자를 리스트로 넘긴다.
- 자격 증명 프롬프트, LFS 내려받기, 훅을 끈다.
- 시간 제한이 있고, 지정한 폴더가 크기 한도를 넘으면 도중에 멈춘다.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class GitError(Exception):
    """git 명령이 실패했다."""

    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


class GitTimeout(GitError):
    """git 명령이 제한 시간을 넘었다."""


class GitTooLarge(GitError):
    """작업 폴더가 크기 한도를 넘었다."""


_POLL_SECONDS = 1.0
_NO_HOOKS = Path(tempfile.gettempdir()) / "codemap-no-hooks"


def dir_size_bytes(path: Path) -> int:
    """폴더 안 파일 크기의 합. 심볼릭 링크는 따라가지 않는다."""
    total = 0
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        try:
                            total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
        except OSError:
            pass
    return total


def _kill_tree(proc: subprocess.Popen) -> None:
    """git이 띄운 하위 프로세스(git-remote-https 등)까지 함께 종료한다."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def run_git(
    args: list[str],
    cwd: Path | None = None,
    timeout: float = 300,
    allow_local: bool = False,
    watch_dir: Path | None = None,
    max_bytes: int | None = None,
) -> str:
    """git을 실행하고 stdout을 돌려준다. 실패하면 GitError(하위: GitTimeout, GitTooLarge)."""
    _NO_HOOKS.mkdir(exist_ok=True)
    cmd = [
        "git",
        "-c", f"core.hooksPath={_NO_HOOKS}",
        "-c", "protocol.ext.allow=never",
        "-c", f"protocol.file.allow={'user' if allow_local else 'never'}",
        *args,
    ]
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
    # 출력은 파이프 대신 임시 파일로 받는다. 파이프가 가득 차 git이 멈추는 일을 피한다.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=os.name != "nt",
            )
        except OSError as e:
            raise GitError(f"git을 실행하지 못했어요: {e}") from e

        deadline = time.monotonic() + timeout
        while True:
            try:
                proc.wait(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
            if time.monotonic() > deadline:
                _kill_tree(proc)
                proc.wait()
                raise GitTimeout(f"git {args[0]}이(가) {timeout:.0f}초를 넘었어요")
            if (
                watch_dir is not None
                and max_bytes is not None
                and dir_size_bytes(watch_dir) > max_bytes
            ):
                _kill_tree(proc)
                proc.wait()
                raise GitTooLarge(f"작업 폴더가 {max_bytes} 바이트를 넘었어요")

        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", errors="replace")
        stderr = err.read().decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise GitError(f"git {args[0]} 실패({proc.returncode}): {stderr.strip()[:500]}", proc.returncode)
    return stdout


def remove_tree(path: Path) -> None:
    """읽기 전용 파일(.git 객체)이 있어도 Windows에서 지워지게 한다."""
    if not path.exists():
        return

    def _make_writable_and_retry(func, p, _exc):
        os.chmod(p, 0o700)
        func(p)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=_make_writable_and_retry)
