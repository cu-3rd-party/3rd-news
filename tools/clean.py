from pathlib import Path
from shutil import rmtree

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {".git", ".venv", "node_modules"}
REMOVE_DIRECTORIES = {
    ".benchmarks",
    ".basedpyright",
    ".cache",
    ".hypothesis",
    ".mypy_cache",
    ".mutmut-cache",
    ".nox",
    ".pyright",
    ".pytype",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".ty_cache",
    ".vite",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "htmlcov",
    "mutants",
    "site",
    "test-results",
}


def clean_tree(root: Path) -> None:
    directories: list[Path] = []
    files: list[Path] = []
    pending = [root]
    while pending:
        parent = pending.pop()
        for path in parent.iterdir():
            if path.is_symlink():
                continue
            if path.is_dir():
                if path.name in SKIP_DIRECTORIES:
                    continue
                if path.name in REMOVE_DIRECTORIES or path.name.endswith((".egg", ".egg-info")):
                    directories.append(path)
                else:
                    pending.append(path)
            elif (
                path.name == ".DS_Store"
                or path.name == ".coverage"
                or path.name.startswith(".coverage.")
                or path.name in {".coverage.json", "coverage.json", "junit.xml"}
                or path.name == "coverage.xml"
                or (path.name.startswith("junit") and path.suffix == ".xml")
                or path.suffix == ".egg"
                or path.suffix in {".prof", ".pyc", ".pyo"}
            ):
                files.append(path)
    for path in directories:
        rmtree(path)
    for path in files:
        path.unlink(missing_ok=True)


def clean() -> None:
    clean_tree(ROOT)
