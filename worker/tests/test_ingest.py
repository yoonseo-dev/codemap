"""수집(INGEST) 테스트. 로컬 임시 git 저장소만 쓰고 인터넷이 필요 없다."""

import os
import time
from pathlib import Path

import pytest
from gitrepo import Repo

from codemap_worker.ingest import IngestConfig, ensure_checkout, ingest
from codemap_worker.ingest import clone as clone_mod
from codemap_worker.ingest.files import collect_files
from codemap_worker.ingest.git import GitError, GitTimeout, run_git
from codemap_worker.ingest.info import count_commits
from codemap_worker.models import StageError


def cfg(tmp_path: Path, **kw) -> IngestConfig:
    return IngestConfig(workdir=tmp_path / "work", allow_local_repos=True, **kw)


def reports():
    seen: list[tuple] = []
    return seen, lambda p, d, m: seen.append((p, d, m))


@pytest.fixture
def repo(tmp_path) -> Repo:
    r = Repo(tmp_path / "src")
    r.commit({"a.py": "def f():\n    pass\n", "README.md": "hi"}, "first")
    r.commit({"pkg/b.py": "def g():\n    pass\n", "lib/C.java": "class C {}\n"}, "second")
    return r


def head(repo: Repo) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=repo.path).strip()


def test_ingest_returns_real_commit_info_and_source_files(tmp_path, repo):
    seen, report = reports()

    result = ingest(str(repo.path), head(repo), cfg(tmp_path), report)

    assert result.commit.branch == "trunk"
    assert result.commit.commit_date.tzinfo is not None
    assert (result.commit.commits, result.commit.bulk_excluded) == (2, 0)
    assert [f.path for f in result.collected.files] == ["a.py", "lib/C.java", "pkg/b.py"]
    assert {f.language for f in result.collected.files} == {"python", "java"}
    # README.md 같은 소스가 아닌 파일은 sparse checkout으로 받지도 않는다
    assert not (result.root / "README.md").exists()
    assert seen[-1][1] == "커밋 2개를 받고 대량 커밋 0개는 뺐어요"
    assert seen[-1][2] == {"commits": 2, "bulkExcluded": 0, "sourceFiles": 3}
    percents = [p for p, _, _ in seen]
    assert percents == sorted(percents) and percents[-1] == 100


def test_checks_out_the_requested_commit_not_the_latest(tmp_path, repo):
    first = head(repo)
    repo.commit({"new.py": "x = 1\n"}, "third")

    result = ingest(str(repo.path), first, cfg(tmp_path), lambda *a: None)

    assert "new.py" not in [f.path for f in result.collected.files]
    assert result.commit.commits == 2  # 요청한 커밋 이전의 이력만 센다


def test_second_call_reuses_the_checkout_without_cloning_again(tmp_path, repo, monkeypatch):
    c = cfg(tmp_path)
    sha = head(repo)
    first = ensure_checkout(str(repo.path), sha, c)
    calls = []
    real = clone_mod.run_git
    monkeypatch.setattr(clone_mod, "run_git", lambda *a, **k: (calls.append(a), real(*a, **k))[1])

    second = ensure_checkout(str(repo.path), sha, c)

    assert second == first and calls == []


def test_half_finished_checkout_is_removed_and_downloaded_again(tmp_path, repo):
    c = cfg(tmp_path)
    sha = head(repo)
    dest = clone_mod.checkout_dir(str(repo.path), sha, c)
    dest.mkdir(parents=True)
    (dest / "junk.txt").write_text("left over")  # 완료 표시가 없는 폴더

    ensure_checkout(str(repo.path), sha, c)

    assert not (dest / "junk.txt").exists() and (dest / "a.py").exists()


def test_bulk_commits_are_counted_but_not_dropped_from_the_total():
    log = "\n".join([
        "@@aaa", "a.py", "b.py", "",
        "@@bbb", *[f"f{i}.py" for i in range(50)], "",
        "@@ccc", *[f"g{i}.py" for i in range(49)],
    ])
    assert count_commits(log, bulk_threshold=50) == (3, 1)
    assert count_commits("", 50) == (0, 0)


def test_bulk_commit_in_a_real_repo(tmp_path):
    r = Repo(tmp_path / "bulk")
    r.commit({"a.py": "x=1\n"})
    r.commit({f"m{i}.py": f"v={i}\n" for i in range(5)}, "rename everything")
    sha = head(r)

    result = ingest(str(r.path), sha, cfg(tmp_path, bulk_threshold=5), lambda *a: None)

    assert (result.commit.commits, result.commit.bulk_excluded) == (2, 1)


def test_max_commits_limits_the_range(tmp_path, repo):
    result = ingest(str(repo.path), head(repo), cfg(tmp_path, max_commits=1), lambda *a: None)
    assert result.commit.commits == 1


def test_too_large_repository_is_rejected_and_the_folder_removed(tmp_path):
    r = Repo(tmp_path / "big")
    r.commit({"huge.py": "x = '" + "a" * 3_000_000 + "'\n"})
    c = IngestConfig(workdir=tmp_path / "work", allow_local_repos=True, max_repo_mb=1,
                     max_file_kb=10_000)

    with pytest.raises(StageError) as e:
        ingest(str(r.path), head(r), c, lambda *a: None)

    assert (e.value.code, e.value.resumable) == ("REPO_TOO_LARGE", False)
    assert list((tmp_path / "work").iterdir()) == []


def test_repository_without_java_or_python_is_unsupported(tmp_path):
    r = Repo(tmp_path / "docs")
    r.commit({"README.md": "hello", "main.go": "package main"})

    with pytest.raises(StageError) as e:
        ingest(str(r.path), head(r), cfg(tmp_path), lambda *a: None)

    assert (e.value.code, e.value.resumable) == ("UNSUPPORTED_LANGUAGE", False)


@pytest.mark.parametrize("url", [
    "http://github.com/o/r", "https://gitlab.com/o/r", "https://github.com/o", "file:///etc",
    "--upload-pack=evil", "https://github.com/o/r/tree/main", "git@github.com:o/r.git",
    "/definitely/not/there",
])
def test_unsafe_or_unknown_addresses_are_rejected_before_any_git_call(tmp_path, url):
    with pytest.raises(StageError) as e:
        ensure_checkout(url, "a" * 40, IngestConfig(workdir=tmp_path / "w", allow_local_repos=True))
    assert (e.value.code, e.value.resumable) == ("CLONE_FAILED", False)
    assert not (tmp_path / "w").exists()


def test_local_paths_are_rejected_in_production_mode(tmp_path, repo):
    with pytest.raises(StageError) as e:
        ensure_checkout(str(repo.path), head(repo), IngestConfig(workdir=tmp_path / "w"))
    assert e.value.code == "CLONE_FAILED"


def test_bad_commit_sha_is_clone_failed_and_leaves_nothing_behind(tmp_path, repo):
    with pytest.raises(StageError) as e:
        ensure_checkout(str(repo.path), "f" * 40, cfg(tmp_path))
    assert (e.value.code, e.value.resumable) == ("CLONE_FAILED", True)
    assert list((tmp_path / "work").iterdir()) == []


def test_sha_that_looks_like_an_option_is_rejected(tmp_path, repo):
    with pytest.raises(StageError):
        ensure_checkout(str(repo.path), "--help", cfg(tmp_path))


def test_failed_git_command_is_a_git_error():
    with pytest.raises(GitError) as e:
        run_git(["definitely-not-a-git-command"])
    assert not isinstance(e.value, GitTimeout)


def test_slow_git_command_times_out_and_is_killed(monkeypatch):
    # git alias로 "오래 걸리는 명령"을 만든다 (git이 셸을 거쳐 python을 실행)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "alias.slow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "!python -c \"import time; time.sleep(30)\"")
    started = time.monotonic()

    with pytest.raises(GitTimeout):
        run_git(["slow"], timeout=2)

    assert time.monotonic() - started < 15  # 30초를 기다리지 않고 끝났다


def test_collect_files_skips_excluded_dirs_large_files_and_symlinks(tmp_path):
    root = tmp_path / "r"
    for rel, text in {
        "src/app.py": "x=1\n", "src/Main.java": "class M {}\n", "node_modules/x/y.py": "z=1\n",
        "build/gen.java": "class G {}\n", ".git/hooks/h.py": "h=1\n", "docs/readme.md": "r",
        "src/big.py": "#" * 5000,
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    try:
        os.symlink(root / "src" / "app.py", root / "src" / "link.py")
        symlinks = 1
    except (OSError, NotImplementedError):
        symlinks = 0  # Windows에서 권한이 없으면 링크 검사는 건너뛴다

    got = collect_files(root, max_file_kb=1)

    assert [f.path for f in got.files] == ["src/Main.java", "src/app.py"]
    assert got.skipped_large == 1
    assert got.skipped_symlink == symlinks
