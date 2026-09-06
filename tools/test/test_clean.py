from pathlib import Path

from tools.clean import clean_tree


def test_clean_removes_generated_artifacts_without_touching_dependencies(tmp_path: Path) -> None:
    removable = [
        tmp_path / ".pytest_cache",
        tmp_path / "nested" / "__pycache__",
        tmp_path / "nested" / ".benchmarks",
        tmp_path / "package.egg-info",
        tmp_path / "package.egg",
        tmp_path / "artifacts",
        tmp_path / "build",
        tmp_path / "web" / "dist",
        tmp_path / ".basedpyright",
        tmp_path / ".nox",
        tmp_path / ".pytype",
        tmp_path / ".pyright",
        tmp_path / ".mutmut-cache",
        tmp_path / "mutants",
        tmp_path / "site",
        tmp_path / "test-results",
    ]
    retained = [tmp_path / ".venv" / "build", tmp_path / "node_modules" / "dist"]
    for directory in [*removable, *retained]:
        directory.mkdir(parents=True)
        (directory / "artifact").write_text("x")
    generated_files = (
        ".coverage",
        ".coverage.json",
        "coverage.json",
        "coverage.xml",
        "junit.xml",
        "junit-unit.xml",
        "built.egg",
        "profile.prof",
        ".DS_Store",
        "module.pyc",
    )
    for filename in generated_files:
        (tmp_path / filename).write_text("x")

    clean_tree(tmp_path)

    assert not any(path.exists() for path in removable)
    assert all(path.exists() for path in retained)
    assert not any((tmp_path / filename).exists() for filename in generated_files)
