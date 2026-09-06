import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = (
    "packages/python/contracts",
    "services/main",
    "services/classifier-ai",
    "services/classifier-regex",
    "services/parser-rss",
    "services/parser-time",
    "tools",
)


def run(action: str) -> None:
    if action not in {
        "sync",
        "test",
        "lint",
        "fmt",
        "integration",
        "mutation",
        "audit",
        "sql",
    }:
        raise ValueError(f"unknown quality action: {action}")
    if action == "sql":
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        project = ROOT / "services/main"
        config = Config(str(project / "alembic.ini"))
        config.set_main_option("script_location", str(project / "alembic"))
        script = ScriptDirectory.from_config(config)
        with tempfile.TemporaryDirectory(prefix="thirdnews-sql-") as temporary:
            for revision in reversed(list(script.walk_revisions())):
                sql = Path(temporary) / f"{revision.revision}.sql"
                with sql.open("w") as output:
                    subprocess.run(
                        [
                            "uv",
                            "run",
                            "--locked",
                            "--all-groups",
                            "alembic",
                            "upgrade",
                            f"{revision.down_revision or 'base'}:{revision.revision}",
                            "--sql",
                        ],
                        cwd=project,
                        stdout=output,
                        check=True,
                    )
                subprocess.run(
                    ["uv", "run", "--locked", "--all-groups", "squawk", str(sql)],
                    cwd=project,
                    check=True,
                )
        return
    for relative in PROJECTS:
        project = ROOT / relative
        if action == "sync":
            commands = [["uv", "sync", "--locked", "--all-groups"]]
        elif action == "lint":
            commands = [
                ["ruff", "format", "--check", "."],
                ["ruff", "check", "."],
                ["ty", "check"],
                ["basedpyright"],
            ]
        elif action == "fmt":
            commands = [["ruff", "check", "--fix", "."], ["ruff", "format", "."]]
        elif action in ("test", "integration"):
            expression = "not integration and not e2e" if action == "test" else "integration or e2e"
            commands = (
                [["pytest", "-m", expression]]
                if any((project / name).is_dir() for name in ("test", "tests"))
                and (action == "test" or relative == "services/main")
                else []
            )
        elif action == "mutation":
            commands = (
                [
                    [
                        "pytest",
                        "--gremlins",
                        "--gremlin-targets=lib/domain",
                        "--gremlin-report=json",
                        "test/test_domain.py",
                    ]
                ]
                if relative == "services/main"
                else []
            )
        else:
            commands = [
                [
                    str(ROOT / "services/main/.venv/bin/pip-audit"),
                    "--path",
                    str(project / ".venv/lib/python3.14/site-packages"),
                ]
            ]
        for command in commands:
            print(f"[{relative}] {' '.join(command)}", flush=True)
            invocation = (
                command
                if command[0] == "uv" or Path(command[0]).is_absolute()
                else ["uv", "run", "--locked", "--all-groups", *command]
            )
            subprocess.run(invocation, cwd=project, check=True)


def sync() -> None:
    run("sync")


def test() -> None:
    run("test")


def lint() -> None:
    run("lint")


def format() -> None:
    run("fmt")


def integration() -> None:
    run("integration")


def mutation() -> None:
    run("mutation")


def audit() -> None:
    run("audit")


def sql() -> None:
    run("sql")
