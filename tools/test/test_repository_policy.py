import ast
import builtins
import io
import tokenize
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAINTAINED_ROOTS = (
    ROOT / "services",
    ROOT / "packages" / "python",
    ROOT / "tools",
    ROOT / "apps",
    ROOT / "infra",
)
SKIPPED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".ty_cache",
    ".mypy_cache",
    ".hypothesis",
    ".benchmarks",
    ".basedpyright",
    ".mutmut-cache",
    ".nox",
    ".pyright",
    ".pytype",
    "artifacts",
    "build",
    "dist",
    "htmlcov",
    "mutants",
    "site",
    "test-results",
}
CONFIG_NAMES = {
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "Caddyfile",
    "Dockerfile",
    "Makefile",
    "justfile",
}
CONFIG_SUFFIXES = {".ini", ".mako", ".sh", ".toml", ".yaml", ".yml"}
C_STYLE_SUFFIXES = {".css", ".go", ".html", ".js", ".jsx", ".ts", ".tsx"}
BOUNDARY_SUFFIXES = (
    "Adapter",
    "Broker",
    "Client",
    "Database",
    "Fetcher",
    "Gateway",
    "Indexer",
    "ObjectStore",
    "Repository",
    "Store",
    "UnitOfWork",
)


@lru_cache(maxsize=1)
def maintained_files() -> tuple[Path, ...]:
    files = []
    for root in MAINTAINED_ROOTS:
        for parent, directories, filenames in root.walk():
            directories[:] = [
                name
                for name in directories
                if name not in SKIPPED_PARTS and not name.endswith(".egg-info")
            ]
            for filename in filenames:
                path = parent / filename
                if filename == "uv.lock" or filename.endswith(".lock"):
                    continue
                files.append(path)
    return tuple(files)


@lru_cache(maxsize=1)
def python_files() -> tuple[Path, ...]:
    return tuple(path for path in maintained_files() if path.suffix == ".py")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def architecture_root(path: Path) -> tuple[str, ...]:
    parts = path.relative_to(ROOT).parts
    if parts[0] == "services":
        return parts[:2]
    if parts[:3] == ("packages", "python", "contracts"):
        return parts[:3]
    return parts[:1]


def dotted_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = dotted_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    return ""


def module_parts(path: Path) -> tuple[str, ...]:
    parts = path.relative_to(ROOT).with_suffix("").parts
    for anchor in ("lib", "thirdnews_contracts", "tools"):
        if anchor in parts:
            return parts[parts.index(anchor) :]
    return parts


def resolved_import(path: Path, node: ast.ImportFrom) -> tuple[str, ...]:
    imported = tuple((node.module or "").split(".")) if node.module else ()
    if node.level == 0:
        return imported
    current = module_parts(path)
    package = current if path.name == "__init__.py" else current[:-1]
    retained = max(0, len(package) - node.level + 1)
    return (*package[:retained], *imported)


def string_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, (ast.List, ast.Tuple)):
        return bool(node.elts) and all(string_literal(item) for item in node.elts)
    return False


def field_alias(node: ast.AnnAssign) -> str:
    if isinstance(node.value, ast.Call) and dotted_name(node.value.func).split(".")[-1] == "Field":
        for keyword in node.value.keywords:
            if (
                keyword.arg in {"alias", "validation_alias"}
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                return keyword.value.value
    return node.target.id if isinstance(node.target, ast.Name) else ""


def c_style_comment_positions(text: str) -> list[tuple[int, int]]:
    positions = []
    quote = ""
    escaped = False
    line = 1
    column = 0
    index = 0
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if char == "\n":
            line += 1
            column = 0
            escaped = False
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            column += 1
            continue
        if char in {'"', "'", "`"}:
            quote = char
            index += 1
            column += 1
            continue
        if char == "/" and following in {"/", "*"}:
            positions.append((line, column))
            if following == "/":
                newline = text.find("\n", index + 2)
                if newline < 0:
                    break
                index = newline
                continue
            closing = text.find("*/", index + 2)
            if closing < 0:
                break
            fragment = text[index : closing + 2]
            line += fragment.count("\n")
            last_newline = fragment.rfind("\n")
            column = len(fragment) if last_newline < 0 else len(fragment) - last_newline - 1
            index = closing + 2
            continue
        if char == "<" and text[index : index + 4] == "<!--":
            positions.append((line, column))
            closing = text.find("-->", index + 4)
            if closing < 0:
                break
            fragment = text[index : closing + 3]
            line += fragment.count("\n")
            last_newline = fragment.rfind("\n")
            column = len(fragment) if last_newline < 0 else len(fragment) - last_newline - 1
            index = closing + 3
            continue
        index += 1
        column += 1
    return positions


def hash_comment_column(line: str) -> int | None:
    quote = ""
    escaped = False
    for column, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "#":
            return column
    return None


def test_root_legacy_surfaces_are_absent() -> None:
    forbidden = [
        ROOT / ".github",
        ROOT / "scripts",
        ROOT / "tests",
        ROOT / "infra" / "bootstrap.py",
    ]
    assert not [relative(path) for path in forbidden if path.exists()]


def test_maintained_files_have_no_duplicate_number_suffix() -> None:
    candidates = [*maintained_files(), *(path for path in ROOT.iterdir() if path.is_file())]
    duplicates = [
        relative(path)
        for path in candidates
        if path.stem.rpartition(" ")[1] and path.stem.rpartition(" ")[2].isdigit()
    ]
    assert not duplicates


def test_task_runners_invoke_installed_entrypoints() -> None:
    errors = []
    for path in (ROOT / "Makefile", ROOT / "justfile"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "python -" in line or ".py" in line:
                errors.append(f"{relative(path)}:{number} invokes Python source directly")
    assert not errors, "\n".join(errors)


def test_every_service_has_the_required_layout_and_top_router() -> None:
    required_lib = {"core", "domain", "dto", "handlers", "infra", "interactor"}
    errors = []
    for service in sorted((ROOT / "services").iterdir()):
        if not service.is_dir() or service.name.startswith("."):
            continue
        for name in ("main.py", "Dockerfile", "pyproject.toml", "uv.lock", "test"):
            if not (service / name).exists():
                errors.append(f"{service.name}: missing {name}")
        for name in ("app", "bootstrap", "presentation", "requirements.txt", "src", "tests"):
            if (service / name).exists():
                errors.append(f"{service.name}: forbidden legacy path {name}")
        lib = service / "lib"
        missing = required_lib - {path.name for path in lib.iterdir() if path.is_dir()}
        if missing:
            errors.append(f"{service.name}: missing lib folders {sorted(missing)}")
        if not (lib / "handlers" / "top.py").is_file():
            errors.append(f"{service.name}: missing lib/handlers/top.py")
        top_imported = False
        for path in lib.rglob("*.py"):
            if path == lib / "handlers" / "top.py":
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [tuple(item.name.split(".")) for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [resolved_import(path, node)]
                else:
                    modules = []
                if any(module[-2:] == ("handlers", "top") for module in modules):
                    top_imported = True
        if not top_imported:
            errors.append(f"{service.name}: lib/handlers/top.py is not wired")
    assert not errors, "\n".join(errors)


def test_python_files_define_at_most_one_top_level_class() -> None:
    errors = []
    for path in python_files():
        classes = [
            node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef)
        ]
        if len(classes) > 1:
            names = ", ".join(node.name for node in classes)
            errors.append(f"{relative(path)} defines {len(classes)} classes: {names}")
    assert not errors, "\n".join(errors)


def test_exceptions_are_defined_only_in_interactor_errors() -> None:
    definitions = []
    exception_names = {
        name
        for name in dir(builtins)
        if isinstance(value := getattr(builtins, name), type) and issubclass(value, BaseException)
    }
    for path in python_files():
        tree = ast.parse(path.read_text())
        for node in [item for item in ast.walk(tree) if isinstance(item, ast.ClassDef)]:
            definitions.append(
                (path, node, {dotted_name(base).split(".")[-1] for base in node.bases})
            )
    changed = True
    while changed:
        changed = False
        for _, node, bases in definitions:
            inherited_exception = bool(bases & exception_names) or any(
                base.endswith(("Error", "Exception")) for base in bases
            )
            if node.name not in exception_names and inherited_exception:
                exception_names.add(node.name)
                changed = True
    errors = [
        f"{relative(path)}:{node.lineno} {node.name} must be in interactor/errors"
        for path, node, _ in definitions
        if node.name in exception_names
        and not ("interactor" in path.parts and "errors" in path.parts)
    ]
    assert not errors, "\n".join(errors)


def test_domain_and_infrastructure_have_no_legacy_layout() -> None:
    forbidden_roots = (
        ROOT / "admin-ui",
        ROOT / "parsers",
        ROOT / "packages" / "contracts",
    )
    errors = [relative(path) for path in forbidden_roots if path.exists()]
    for path in python_files():
        parts = path.relative_to(ROOT).parts
        if "domain" in parts:
            index = parts.index("domain")
            remainder = parts[index + 1 :]
            if remainder != ("__init__.py",) and (not remainder or remainder[0] != "entities"):
                errors.append(f"{relative(path)} must be under domain/entities")
        if "interactor" in parts:
            index = parts.index("interactor")
            if len(parts) > index + 1 and parts[index + 1] == "ports":
                errors.append(f"{relative(path)} uses legacy interactor/ports")
        if "infra" in parts:
            index = parts.index("infra")
            remainder = parts[index + 1 :]
            allowed = remainder in {("__init__.py",), ("resources.py",)} or (
                bool(remainder) and remainder[0] in {"clients", "storage"}
            )
            if not allowed:
                errors.append(f"{relative(path)} must be under infra/clients or infra/storage")
    contracts = ROOT / "packages" / "python" / "contracts" / "thirdnews_contracts"
    for path in contracts.glob("*.py"):
        if path.name != "__init__.py":
            errors.append(f"{relative(path)} is a legacy flat contract module")
    assert not errors, "\n".join(errors)


def test_inner_layers_do_not_import_infrastructure() -> None:
    errors = []
    for path in python_files():
        parts = path.relative_to(ROOT).parts
        is_domain = "domain" in parts
        is_use_case = "interactor" in parts and "use_cases" in parts
        is_handler = "handlers" in parts
        if not is_domain and not is_use_case and not is_handler:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules.extend(tuple(item.name.split(".")) for item in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(resolved_import(path, node))
            else:
                continue
            for module in modules:
                if is_domain and set(module) & {"core", "dto", "handlers", "infra", "interactor"}:
                    errors.append(f"{relative(path)}:{node.lineno} imports {'.'.join(module)}")
                if is_use_case and set(module) & {"handlers", "infra"}:
                    errors.append(f"{relative(path)}:{node.lineno} imports {'.'.join(module)}")
                if is_handler and "infra" in module:
                    errors.append(f"{relative(path)}:{node.lineno} imports {'.'.join(module)}")
    assert not errors, "\n".join(errors)


def test_python_source_has_no_comments_or_docstrings() -> None:
    errors = []
    for path in python_files():
        source = path.read_text()
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    if (
                        token.start == (1, 0)
                        and token.string.startswith("#!")
                        and path.stat().st_mode & 0o111
                    ):
                        continue
                    errors.append(f"{relative(path)}:{token.start[0]} comment")
        except tokenize.TokenError as error:
            errors.append(f"{relative(path)} tokenize error: {error}")
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            errors.append(f"{relative(path)} syntax error: {error}")
            continue
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    errors.append(f"{relative(path)}:{node.body[0].lineno} docstring")
    assert not errors, "\n".join(errors)


def test_javascript_css_html_and_config_source_has_no_comments() -> None:
    errors = []
    candidates = [
        path
        for path in maintained_files()
        if path.suffix in C_STYLE_SUFFIXES
        or path.suffix in CONFIG_SUFFIXES
        or path.name in CONFIG_NAMES
    ]
    candidates.extend(
        path
        for path in ROOT.iterdir()
        if path.is_file() and (path.name in CONFIG_NAMES or path.suffix in CONFIG_SUFFIXES)
    )
    for path in sorted(set(candidates)):
        text = path.read_text(errors="replace")
        if path.suffix in C_STYLE_SUFFIXES:
            for line, column in c_style_comment_positions(text):
                errors.append(f"{relative(path)}:{line}:{column + 1} comment")
            continue
        if path.suffix == ".mako" and ('"""' in text or "'''" in text):
            errors.append(f"{relative(path)} template docstring")
        for number, line in enumerate(text.splitlines(), start=1):
            column = hash_comment_column(line)
            required_shebang = (
                number == 1
                and column == 0
                and line.startswith("#!")
                and path.stat().st_mode & 0o111
            )
            if column is not None and not required_shebang:
                errors.append(f"{relative(path)}:{number}:{column + 1} comment")
    assert not errors, "\n".join(errors)


def test_python_source_has_no_cli_or_direct_environment_access() -> None:
    errors = []
    for path in python_files():
        tree = ast.parse(path.read_text())
        os_names = {"os"}
        sys_names = {"sys"}
        forbidden_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name == "argparse":
                        errors.append(f"{relative(path)}:{node.lineno} argparse")
                    if item.name == "os":
                        os_names.add(item.asname or item.name)
                    if item.name == "sys":
                        sys_names.add(item.asname or item.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "argparse":
                    errors.append(f"{relative(path)}:{node.lineno} argparse")
                if node.module == "os":
                    for item in node.names:
                        if item.name in {"environ", "getenv", "getenvb"}:
                            forbidden_names.add(item.asname or item.name)
                if node.module == "sys":
                    for item in node.names:
                        if item.name == "argv":
                            forbidden_names.add(item.asname or item.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                errors.append(f"{relative(path)}:{node.lineno} {node.id}")
            if not isinstance(node, ast.Attribute):
                continue
            owner = dotted_name(node.value)
            if owner in os_names and node.attr in {"environ", "getenv", "getenvb"}:
                errors.append(f"{relative(path)}:{node.lineno} {owner}.{node.attr}")
            if owner in sys_names and node.attr == "argv":
                errors.append(f"{relative(path)}:{node.lineno} {owner}.argv")
    assert not errors, "\n".join(sorted(set(errors)))


def test_other_source_has_no_direct_or_non_atomic_environment_access() -> None:
    errors = []
    direct_access = ("import.meta.env", "process.env", "Bun.env", "Deno.env")
    forbidden_names = ("_URL", "_URI", "_DSN", "_ENDPOINT")
    for path in maintained_files():
        if path.suffix not in C_STYLE_SUFFIXES:
            continue
        text = path.read_text(errors="replace")
        for access in direct_access:
            if access in text:
                errors.append(f"{relative(path)} directly reads {access}")
    candidates = [
        path
        for path in maintained_files()
        if path.suffix in CONFIG_SUFFIXES or path.name in CONFIG_NAMES
    ]
    candidates.extend(
        path
        for path in ROOT.iterdir()
        if path.is_file() and (path.name in CONFIG_NAMES or path.suffix in CONFIG_SUFFIXES)
    )
    for path in sorted(set(candidates)):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            if "${" not in line:
                continue
            if any(
                fragment in line.split("${", 1)[1].split("}", 1)[0] for fragment in forbidden_names
            ):
                errors.append(f"{relative(path)}:{number} uses a non-atomic environment name")
    assert not errors, "\n".join(errors)


def test_settings_use_fixed_env_files_and_atomic_connections() -> None:
    errors = []
    forbidden_fragments = ("_URL", "_URI", "_DSN", "_ENDPOINT")
    for path in python_files():
        tree = ast.parse(path.read_text())
        for node in [item for item in ast.walk(tree) if isinstance(item, ast.ClassDef)]:
            if "BaseSettings" not in {dotted_name(base).split(".")[-1] for base in node.bases}:
                continue
            model_config = next(
                (
                    item.value
                    for item in node.body
                    if isinstance(item, (ast.Assign, ast.AnnAssign))
                    and any(
                        isinstance(target, ast.Name) and target.id == "model_config"
                        for target in (
                            item.targets if isinstance(item, ast.Assign) else [item.target]
                        )
                    )
                ),
                None,
            )
            env_file = None
            if isinstance(model_config, ast.Call):
                env_file = next(
                    (
                        keyword.value
                        for keyword in model_config.keywords
                        if keyword.arg == "env_file"
                    ),
                    None,
                )
            if env_file is None or not string_literal(env_file):
                errors.append(f"{relative(path)}:{node.lineno} requires a fixed env_file")
            aliases = {
                field_alias(item).upper()
                for item in node.body
                if isinstance(item, ast.AnnAssign) and field_alias(item)
            }
            for alias in aliases:
                if any(fragment in alias for fragment in forbidden_fragments):
                    errors.append(f"{relative(path)}:{node.lineno} non-atomic setting {alias}")
            for alias in aliases:
                if not alias.endswith("_SCHEME"):
                    continue
                prefix = alias[: -len("_SCHEME")]
                for part in ("HOST", "PORT"):
                    expected = f"{prefix}_{part}"
                    if expected not in aliases:
                        errors.append(f"{relative(path)}:{node.lineno} missing {expected}")
    assert not errors, "\n".join(errors)


def test_boundary_implementations_explicitly_inherit_interfaces() -> None:
    interface_names: dict[tuple[str, ...], set[str]] = {}
    for path in python_files():
        if "interactor" not in path.parts or "interfaces" not in path.parts:
            continue
        tree = ast.parse(path.read_text())
        interface_names.setdefault(architecture_root(path), set()).update(
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
        )
    errors = []
    for path in python_files():
        if "infra" not in path.parts:
            continue
        if "models" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in [item for item in tree.body if isinstance(item, ast.ClassDef)]:
            if node.name.startswith("_"):
                continue
            if not ({"clients", "storage"} & set(path.parts)):
                if node.name.endswith(BOUNDARY_SUFFIXES):
                    errors.append(
                        f"{relative(path)}:{node.lineno} {node.name} must be in clients or storage"
                    )
                continue
            if node.name == "Base" or node.name.endswith(("Parser", "RepositoryBase", "Resolver")):
                continue
            bases = {dotted_name(base).split(".")[-1] for base in node.bases}
            if not bases & interface_names.get(architecture_root(path), set()):
                errors.append(
                    f"{relative(path)}:{node.lineno} {node.name} must inherit an interface"
                )
    assert not errors, "\n".join(errors)


def test_example_environment_is_atomic_and_comment_free() -> None:
    path = ROOT / ".env.example"
    lines = [line for line in path.read_text().splitlines() if line]
    names = {line.split("=", 1)[0] for line in lines}
    forbidden = {name for name in names if name.endswith(("_URL", "_URI", "_DSN", "_ENDPOINT"))}
    assert not forbidden
    generated_secrets = {
        "AUTH_PRIVATE_KEY",
        "AUTH_PUBLIC_KEY",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "BROKER_TOKEN",
        "DB_PASSWORD",
        "FILE_ACCESS_KEY",
        "FILE_SECRET_KEY",
        "RAW_AUDIT_ENCRYPTION_KEY",
        "SEARCH_KEY",
    }
    assert not names & generated_secrets
    required = {
        "DB_SCHEME",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "BROKER_SCHEME",
        "BROKER_HOST",
        "BROKER_PORT",
        "SEARCH_SCHEME",
        "SEARCH_HOST",
        "SEARCH_PORT",
        "FILE_SCHEME",
        "FILE_HOST",
        "FILE_PORT",
        "FILE_BUCKET",
        "FILE_REGION",
        "PUBLIC_API_SCHEME",
        "PUBLIC_API_HOST",
        "PUBLIC_API_PORT",
        "FILE_PUBLIC_SCHEME",
        "FILE_PUBLIC_HOST",
        "FILE_PUBLIC_PORT",
        "NEWS_SCHEME",
        "NEWS_HOST",
        "NEWS_PORT",
        "TIME_SCHEME",
        "TIME_HOST",
        "TIME_PORT",
    }
    assert required <= names
