"""Curated, current engineering standards keyed by technology profile.

Detection answers *what* the stack is (see opencontext_profiles); this answers
*how to work in it well*: the formatter, the static and dynamic reviewers, the
test runner, and the few code standards that matter most — phrased as runnable
commands so an agent (or a human) can act on them directly.

The four reviewer buckets mirror a real review pipeline:
  * formatter          — deterministic layout, run first
  * static_reviewers   — lint, type-check, static security (no execution)
  * dynamic_reviewers  — tests-with-coverage, runtime/dependency security
  * standards          — code conventions / latest-version guidance

This is plain data, deliberately. Adding a stack means adding a dict entry, not
code. Unknown stacks fall back to GENERIC.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StackStandards:
    """Engineering standards for one detected technology."""

    profile: str
    title: str
    formatter: tuple[str, ...]
    static_reviewers: tuple[str, ...]
    dynamic_reviewers: tuple[str, ...]
    testing: tuple[str, ...]
    standards: tuple[str, ...]


GENERIC = StackStandards(
    profile="generic",
    title="General",
    formatter=("Use the repository's configured formatter; add one if none exists.",),
    static_reviewers=(
        "Run the project's linter and (if typed) its type checker in CI.",
        "Scan dependencies for known CVEs on every change.",
    ),
    dynamic_reviewers=("Run the test suite with coverage reported, not just pass/fail.",),
    testing=("Test observable behavior at boundaries; keep tests deterministic and isolated.",),
    standards=(
        "Pin dependencies with a lockfile.",
        "Gate merges on format-check + lint + tests.",
    ),
)


_CATALOG: dict[str, StackStandards] = {
    "python": StackStandards(
        profile="python",
        title="Python",
        formatter=("ruff format .",),
        static_reviewers=("ruff check .", "mypy .", "bandit -r ."),
        dynamic_reviewers=("pytest --cov", "pip-audit"),
        testing=("pytest — prefer fixtures over setup/teardown; one behavior per test.",),
        standards=(
            "Target the `requires-python` in pyproject.toml; type-annotate public APIs.",
            "Prefer pathlib, dataclasses, and the stdlib before adding a dependency.",
            "Pin with a lockfile (uv or pip-tools).",
        ),
    ),
    "django": StackStandards(
        profile="django",
        title="Django",
        formatter=("ruff format .",),
        static_reviewers=("ruff check .", "mypy .", "python manage.py check --deploy"),
        dynamic_reviewers=("python manage.py test", "pip-audit"),
        testing=("Django test runner or pytest-django; use factories, not fixtures of raw rows.",),
        standards=(
            "Keep migrations in version control and reviewed; never edit applied migrations.",
            "Use the ORM safely — select_related/prefetch_related to avoid N+1.",
        ),
    ),
    "fastapi": StackStandards(
        profile="fastapi",
        title="FastAPI",
        formatter=("ruff format .",),
        static_reviewers=("ruff check .", "mypy ."),
        dynamic_reviewers=("pytest --cov", "pip-audit"),
        testing=("pytest with httpx.AsyncClient / TestClient; test the schema, not internals.",),
        standards=(
            "Pydantic v2 models for request/response; never trust unvalidated input.",
            "Async all the way down — no blocking calls in async handlers.",
        ),
    ),
    "node": StackStandards(
        profile="node",
        title="Node.js",
        formatter=("prettier --write .",),
        static_reviewers=("eslint .", "tsc --noEmit"),
        dynamic_reviewers=("npm test -- --coverage", "npm audit"),
        testing=("vitest or jest; test public behavior, mock only at I/O boundaries.",),
        standards=(
            "ESM modules; declare a Node LTS in package.json `engines`.",
            "No floating promises; handle every rejection.",
        ),
    ),
    "react": StackStandards(
        profile="react",
        title="React",
        formatter=("prettier --write .",),
        static_reviewers=("eslint . (with eslint-plugin-react-hooks)", "tsc --noEmit"),
        dynamic_reviewers=(
            "vitest + @testing-library/react --coverage",
            "axe accessibility checks on key views",
        ),
        testing=("Testing Library — query by role/text, not test ids; avoid snapshot-only tests.",),
        standards=(
            "Function components + hooks; stable, meaningful keys in lists.",
            "Reach for memo/useMemo only after measuring a real cost.",
        ),
    ),
    "next": StackStandards(
        profile="next",
        title="Next.js",
        formatter=("prettier --write .",),
        static_reviewers=("next lint", "tsc --noEmit"),
        dynamic_reviewers=("vitest --coverage", "npm audit"),
        testing=("Testing Library for components; Playwright for routes/e2e.",),
        standards=(
            "Be deliberate about Server vs Client components; keep secrets server-side.",
            "Use the framework's data-fetching/cache primitives over ad-hoc fetches.",
        ),
    ),
    "go": StackStandards(
        profile="go",
        title="Go",
        formatter=("gofmt -w .  (or: go fmt ./...)",),
        static_reviewers=("go vet ./...", "staticcheck ./...", "golangci-lint run"),
        dynamic_reviewers=("go test -race -cover ./...", "govulncheck ./..."),
        testing=("Table-driven tests; always run with -race in CI.",),
        standards=(
            "Wrap errors with %w; accept interfaces, return structs.",
            "context.Context is the first parameter for anything cancellable.",
        ),
    ),
    "rust": StackStandards(
        profile="rust",
        title="Rust",
        formatter=("cargo fmt",),
        static_reviewers=("cargo clippy -- -D warnings",),
        dynamic_reviewers=("cargo test", "cargo audit"),
        testing=("Unit tests in-module (#[cfg(test)]); integration tests under tests/.",),
        standards=(
            "Prefer Result over panic in libraries; reserve unwrap for tests/prototypes.",
            "Deny warnings in CI; keep unsafe blocks small and commented.",
        ),
    ),
    "rails": StackStandards(
        profile="rails",
        title="Ruby on Rails",
        formatter=("rubocop -A",),
        static_reviewers=("rubocop", "brakeman -q"),
        dynamic_reviewers=(
            "bin/rails test  (or: bundle exec rspec)",
            "bundle audit check --update",
        ),
        testing=("Minitest or RSpec; use fixtures/factories; test models and requests.",),
        standards=(
            "Fat models / skinny controllers; keep migrations reversible.",
            "Strong parameters everywhere; never interpolate user input into SQL.",
        ),
    ),
    "java_spring": StackStandards(
        profile="java_spring",
        title="Java / Spring",
        formatter=("google-java-format / mvn spotless:apply",),
        static_reviewers=("mvn checkstyle:check", "spotbugs", "pmd"),
        dynamic_reviewers=("mvn test  (with JaCoCo coverage)", "OWASP dependency-check"),
        testing=("JUnit 5 + Mockito; @SpringBootTest sparingly, slice tests by default.",),
        standards=(
            "Constructor injection over field injection; immutable DTOs.",
            "Keep controllers thin; validate at the boundary with Bean Validation.",
        ),
    ),
    "dotnet": StackStandards(
        profile="dotnet",
        title=".NET",
        formatter=("dotnet format",),
        static_reviewers=("dotnet build -warnaserror", "Roslyn analyzers enabled"),
        dynamic_reviewers=(
            'dotnet test --collect:"XPlat Code Coverage"',
            "dotnet list package --vulnerable",
        ),
        testing=("xUnit/NUnit; arrange-act-assert; mock at interfaces.",),
        standards=(
            "Enable nullable reference types; treat warnings as errors.",
            "async/await end-to-end; no .Result/.Wait() deadlocks.",
        ),
    ),
    "symfony": StackStandards(
        profile="symfony",
        title="Symfony",
        formatter=("php-cs-fixer fix",),
        static_reviewers=("vendor/bin/phpstan analyse", "vendor/bin/psalm"),
        dynamic_reviewers=("vendor/bin/phpunit --coverage-text", "composer audit"),
        testing=("PHPUnit; WebTestCase for controllers; fixtures for data.",),
        standards=(
            "Typed properties and return types throughout; constructor injection.",
            "Keep services stateless; validate input with the Validator component.",
        ),
    ),
    "laravel": StackStandards(
        profile="laravel",
        title="Laravel",
        formatter=("vendor/bin/pint",),
        static_reviewers=("vendor/bin/phpstan analyse  (larastan)",),
        dynamic_reviewers=("vendor/bin/phpunit --coverage-text", "composer audit"),
        testing=("PHPUnit/Pest; use factories and database transactions in tests.",),
        standards=(
            "Form Requests for validation; mass-assignment guarded.",
            "Eager-load relations to avoid N+1; keep business logic out of controllers.",
        ),
    ),
    "drupal": StackStandards(
        profile="drupal",
        title="Drupal",
        formatter=("vendor/bin/phpcbf --standard=Drupal",),
        static_reviewers=(
            "vendor/bin/phpcs --standard=Drupal,DrupalPractice",
            "vendor/bin/phpstan analyse",
        ),
        dynamic_reviewers=("vendor/bin/phpunit", "composer audit"),
        testing=(
            "PHPUnit (Unit/Kernel/Functional); prefer Kernel tests over Functional for speed.",
        ),
        standards=(
            "Use the Drupal coding standards; inject services, never \\Drupal:: in classes.",
            "Config in code (config/sync); update hooks for schema changes.",
        ),
    ),
    "wordpress": StackStandards(
        profile="wordpress",
        title="WordPress",
        formatter=("phpcbf --standard=WordPress",),
        static_reviewers=("phpcs --standard=WordPress", "phpstan analyse"),
        dynamic_reviewers=("phpunit", "composer audit"),
        testing=("PHPUnit with the WP test scaffolding; mock WP functions at the boundary.",),
        standards=(
            "Escape on output, sanitize on input, verify nonces on actions.",
            "Use $wpdb->prepare for every query with variables.",
        ),
    ),
    "terraform": StackStandards(
        profile="terraform",
        title="Terraform",
        formatter=("terraform fmt -recursive",),
        static_reviewers=("terraform validate", "tflint", "tfsec  (or: checkov)"),
        dynamic_reviewers=("terraform plan  (review before every apply)",),
        testing=("terraform validate + plan in CI; consider terratest for modules.",),
        standards=(
            "Remote state with locking; never commit state or secrets.",
            "Pin provider and module versions; small, composable modules.",
        ),
    ),
    "data_ml": StackStandards(
        profile="data_ml",
        title="Data / ML",
        formatter=("ruff format .",),
        static_reviewers=("ruff check .", "mypy ."),
        dynamic_reviewers=("pytest --cov", "pip-audit"),
        testing=("Test data transforms deterministically; pin seeds; small fixture datasets.",),
        standards=(
            "Version data and models, not just code; record experiment configs.",
            "Keep notebooks out of the import path — promote reusable code to modules.",
        ),
    ),
}


#: Profiles with curated standards (excludes pure tooling like make/bazel/uv).
KNOWN_PROFILES = frozenset(_CATALOG)


def is_known(profile: str) -> bool:
    """Whether a profile has curated standards (vs. falling back to GENERIC)."""
    return profile in _CATALOG


def standards_for(profile: str) -> StackStandards:
    """Standards for a profile name, falling back to GENERIC for unknown stacks."""
    return _CATALOG.get(profile, GENERIC)


def render_stack_standards(profile_names: list[str]) -> str:
    """Render Markdown engineering standards for the detected profiles.

    Unknown/duplicate names collapse to a single GENERIC section. With no known
    profiles, returns the GENERIC section so the output is always actionable.
    """

    seen: set[str] = set()
    chosen: list[StackStandards] = []
    for name in profile_names:
        std = standards_for(name)
        if std.profile in seen:
            continue
        seen.add(std.profile)
        chosen.append(std)
    if not chosen:
        chosen = [GENERIC]

    lines = [
        "## Engineering standards (detected stack)",
        "",
        "Derived from the detected stack. Run these before committing; "
        "OpenContext's verified-context gates assume them.",
        "",
    ]
    for std in chosen:
        lines.append(f"### {std.title}")
        lines.append(f"- **Format:** {_join(std.formatter)}")
        lines.append(f"- **Static review:** {_join(std.static_reviewers)}")
        lines.append(f"- **Dynamic review:** {_join(std.dynamic_reviewers)}")
        lines.append(f"- **Testing:** {_join(std.testing)}")
        lines.append(f"- **Standards:** {_join(std.standards)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _join(items: tuple[str, ...]) -> str:
    return "  ·  ".join(items) if items else "—"
