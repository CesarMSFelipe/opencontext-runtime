"""Marker-based first-party technology profiles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from opencontext_core.models.project import ProjectFile, Symbol
from opencontext_core.project.profiles import (
    ContextProviderReference,
    FileClassificationResult,
    ProfileDetectionResult,
    SafeCommand,
    WorkflowPackReference,
)


@dataclass(frozen=True)
class MarkerProfileSpec:
    """Declarative marker profile for broad first-party stack coverage."""

    name: str
    markers: tuple[str, ...]
    required_any_markers: tuple[str, ...] = ()
    score_divisor: int = 3
    workflow_mode: str = "review"
    validation_commands: tuple[SafeCommand, ...] = ()


class MarkerTechnologyProfile:
    """Base class for profiles that detect projects from path markers."""

    name: str = "generic"
    markers: tuple[str, ...] = ()
    required_any_markers: tuple[str, ...] = ()
    score_divisor: int = 3
    workflow_packs: tuple[WorkflowPackReference, ...] = ()
    validation_commands: tuple[SafeCommand, ...] = ()

    def __init__(self, spec: MarkerProfileSpec | None = None) -> None:
        if spec is None:
            return
        self.name = spec.name
        self.markers = spec.markers
        self.required_any_markers = spec.required_any_markers
        self.score_divisor = spec.score_divisor
        self.workflow_packs = (
            WorkflowPackReference(
                name=f"{spec.name.replace('_', '-')}-review",
                mode=spec.workflow_mode,
            ),
        )
        self.validation_commands = spec.validation_commands

    def detect(
        self,
        project_root: Path,
        paths: Sequence[str] = (),
    ) -> ProfileDetectionResult:
        """Detect this profile from provided project-relative paths."""

        path_list = list(paths) if paths else _discover_paths(project_root)
        matched: list[str] = []
        for path in path_list:
            matched.extend(marker for marker in self.markers if _matches_marker(path, marker))
        unique_markers = sorted(set(matched))
        if self.required_any_markers and not any(
            marker in unique_markers for marker in self.required_any_markers
        ):
            return ProfileDetectionResult(profile=self.name, score=0.0, markers=unique_markers)
        score = min(1.0, len(unique_markers) / max(self.score_divisor, 1))
        return ProfileDetectionResult(profile=self.name, score=score, markers=unique_markers)

    def classify_file(self, path: Path) -> FileClassificationResult | None:
        """Marker profiles do not override core file classification yet."""

        return None

    def extract_symbols(self, file: ProjectFile) -> list[Symbol]:
        """Marker profiles do not add custom symbols yet."""

        return []

    def build_context_providers(self) -> list[ContextProviderReference]:
        """Return profile-specific context provider references."""

        return []

    def suggest_workflows(self) -> list[WorkflowPackReference]:
        """Return profile workflow suggestions."""

        return list(self.workflow_packs)

    def suggest_validation_commands(self) -> list[SafeCommand]:
        """Return validation command suggestions."""

        return list(self.validation_commands)


class DrupalTechnologyProfile(MarkerTechnologyProfile):
    """First-party Drupal profile, not a core dependency."""

    name = "drupal"
    markers = (
        ".info.yml",
        ".services.yml",
        ".routing.yml",
        ".permissions.yml",
        ".links.menu.yml",
        ".module",
        ".install",
        "src/Controller",
        "src/Form",
        "src/Plugin",
        "src/EventSubscriber",
        "templates",
        "components",
        "config/install",
        "config/schema",
    )
    # templates// and components// alone are not Drupal; require a Drupal-specific
    # manifest, hook file, or src/ plugin path.
    required_any_markers = (
        ".info.yml",
        ".services.yml",
        ".routing.yml",
        ".permissions.yml",
        ".links.menu.yml",
        ".module",
        ".install",
        "src/Controller",
        "src/Form",
        "src/Plugin",
        "src/EventSubscriber",
        "config/install",
        "config/schema",
    )
    score_divisor = 4
    workflow_packs = (
        WorkflowPackReference(name="drupal-review", mode="review"),
        WorkflowPackReference(name="drupal-security-audit", mode="audit"),
    )
    validation_commands = (
        SafeCommand(name="phpunit", command=("vendor/bin/phpunit",)),
        SafeCommand(name="phpstan", command=("vendor/bin/phpstan",)),
        SafeCommand(name="phpcs", command=("vendor/bin/phpcs",)),
    )


class SymfonyTechnologyProfile(MarkerTechnologyProfile):
    """First-party Symfony profile."""

    name = "symfony"
    markers = (
        "src/Controller",
        "src/Entity",
        "src/Repository",
        "src/Service",
        "config/routes.yaml",
        "config/services.yaml",
        "config/packages",
        "templates",
        "migrations",
    )
    workflow_packs = (WorkflowPackReference(name="symfony-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="phpunit", command=("vendor/bin/phpunit",)),
        SafeCommand(name="phpstan", command=("vendor/bin/phpstan",)),
    )


class LaravelTechnologyProfile(MarkerTechnologyProfile):
    """First-party Laravel profile."""

    name = "laravel"
    markers = (
        "artisan",
        "composer.json",
        "app/Http/Controllers",
        "app/Models",
        "routes/web.php",
        "routes/api.php",
        "database/migrations",
        "config/app.php",
        "resources/views",
    )
    workflow_packs = (WorkflowPackReference(name="laravel-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="phpunit", command=("vendor/bin/phpunit",)),
        SafeCommand(name="pint", command=("vendor/bin/pint", "--test")),
    )


class NodeTechnologyProfile(MarkerTechnologyProfile):
    """First-party Node.js and TypeScript profile."""

    name = "node"
    markers = (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "vite.config.ts",
        "next.config.js",
        "src/",
        "routes/",
        "components/",
        "tests/",
    )
    # Bare src//routes//components//tests/ are shared with every other ecosystem;
    # require a real Node manifest before claiming the project is Node.
    required_any_markers = (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "vite.config.ts",
        "next.config.js",
    )
    workflow_packs = (WorkflowPackReference(name="node-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="npm_test", command=("npm", "test")),
        SafeCommand(name="npm_lint", command=("npm", "run", "lint")),
    )


class ReactTechnologyProfile(MarkerTechnologyProfile):
    """First-party React profile."""

    name = "react"
    markers = (
        "package.json",
        "src/App.jsx",
        "src/App.tsx",
        "src/components",
        "vite.config.ts",
        "public/index.html",
    )
    # A bare src/components/ dir is not React; require a real manifest or an App entry.
    required_any_markers = (
        "package.json",
        "vite.config.ts",
        "src/App.jsx",
        "src/App.tsx",
        "public/index.html",
    )
    workflow_packs = (WorkflowPackReference(name="react-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="npm_test", command=("npm", "test")),
        SafeCommand(name="npm_lint", command=("npm", "run", "lint")),
    )


class NextTechnologyProfile(MarkerTechnologyProfile):
    """First-party Next.js profile."""

    name = "next"
    markers = (
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "app/page.tsx",
        "pages/index.tsx",
        "src/app",
        "src/pages",
    )
    # Bare src/app/ or src/pages/ dirs are not Next; require a Next config or router entry.
    required_any_markers = (
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "app/page.tsx",
        "pages/index.tsx",
    )
    workflow_packs = (WorkflowPackReference(name="next-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="next_lint", command=("npm", "run", "lint")),
        SafeCommand(name="next_test", command=("npm", "test")),
    )


class PythonTechnologyProfile(MarkerTechnologyProfile):
    """First-party Python project profile."""

    name = "python"
    markers = (
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "src/",
        "tests/",
        "pytest.ini",
        "manage.py",
        "celery.py",
    )
    required_any_markers = (
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "pytest.ini",
        "manage.py",
        "celery.py",
    )
    workflow_packs = (WorkflowPackReference(name="python-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="pytest", command=("pytest",)),
        SafeCommand(name="ruff", command=("ruff", "check", ".")),
        SafeCommand(name="mypy", command=("mypy", ".")),
    )


class DjangoTechnologyProfile(MarkerTechnologyProfile):
    """First-party Django profile."""

    name = "django"
    markers = (
        "manage.py",
        "settings.py",
        "urls.py",
        "wsgi.py",
        "asgi.py",
        "apps.py",
        "migrations/",
        "templates/",
    )
    workflow_packs = (WorkflowPackReference(name="django-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="django_tests", command=("python3", "manage.py", "test")),
    )


class FastApiTechnologyProfile(MarkerTechnologyProfile):
    """First-party FastAPI profile."""

    name = "fastapi"
    markers = (
        "fastapi",
        "APIRouter",
        "uvicorn",
        "routers/",
        "dependencies.py",
        "main.py",
        "tests/",
    )
    required_any_markers = ("fastapi", "APIRouter", "uvicorn")
    workflow_packs = (WorkflowPackReference(name="fastapi-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="pytest", command=("pytest",)),
        SafeCommand(name="ruff", command=("ruff", "check", ".")),
    )


class JavaSpringTechnologyProfile(MarkerTechnologyProfile):
    """First-party Java/Spring project profile."""

    name = "java_spring"
    markers = (
        "pom.xml",
        "build.gradle",
        "settings.gradle",
        "src/main/java",
        "src/test/java",
        "Controller.java",
        "Service.java",
        "Repository.java",
        "Entity.java",
        "application.yml",
        "application.properties",
    )
    workflow_packs = (WorkflowPackReference(name="java-spring-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="maven_test", command=("mvn", "test")),
        SafeCommand(name="gradle_test", command=("./gradlew", "test")),
    )


class DotNetTechnologyProfile(MarkerTechnologyProfile):
    """First-party .NET profile."""

    name = "dotnet"
    markers = (".csproj", ".sln", "Program.cs", "appsettings.json", "Controllers/")


class GoTechnologyProfile(MarkerTechnologyProfile):
    """First-party Go profile."""

    name = "go"
    markers = ("go.mod", "go.sum", "cmd/", "internal/", "_test.go")


class RustTechnologyProfile(MarkerTechnologyProfile):
    """First-party Rust profile."""

    name = "rust"
    markers = ("Cargo.toml", "Cargo.lock", "src/main.rs", "src/lib.rs", "tests/")
    # A bare tests/ dir is not Rust; require a Cargo manifest or a crate entrypoint.
    required_any_markers = ("Cargo.toml", "Cargo.lock", "src/main.rs", "src/lib.rs")


class TerraformTechnologyProfile(MarkerTechnologyProfile):
    """First-party DevOps/Terraform profile."""

    name = "terraform"
    markers = (".tf", ".tfvars", "terraform.lock.hcl", "providers.tf", "variables.tf")


class RailsTechnologyProfile(MarkerTechnologyProfile):
    """First-party Ruby on Rails profile."""

    name = "rails"
    markers = (
        "Gemfile",
        "config/routes.rb",
        "app/controllers",
        "app/models",
        "app/views",
        "db/migrate",
        "spec/",
        "test/",
    )
    workflow_packs = (WorkflowPackReference(name="rails-review", mode="review"),)
    validation_commands = (
        SafeCommand(name="rails_tests", command=("bin/rails", "test")),
        SafeCommand(name="rspec", command=("bundle", "exec", "rspec")),
    )


class WordPressTechnologyProfile(MarkerTechnologyProfile):
    """First-party WordPress profile."""

    name = "wordpress"
    markers = (
        "wp-config.php",
        "wp-content/plugins",
        "wp-content/themes",
        "functions.php",
        "style.css",
        "woocommerce",
    )
    workflow_packs = (WorkflowPackReference(name="wordpress-review", mode="review"),)


class DataMlTechnologyProfile(MarkerTechnologyProfile):
    """First-party data and ML project profile."""

    name = "data_ml"
    markers = (
        "notebooks/",
        ".ipynb",
        "requirements.txt",
        "environment.yml",
        "mlflow",
        "dvc.yaml",
        "sklearn",
        "pytorch",
        "tensorflow",
    )
    workflow_packs = (WorkflowPackReference(name="data-ml-review", mode="review"),)


def additional_marker_profiles() -> list[MarkerTechnologyProfile]:
    """Return broad first-party technology profiles declared from marker specs."""

    return [MarkerTechnologyProfile(spec) for spec in ADDITIONAL_PROFILE_SPECS]


ADDITIONAL_PROFILE_SPECS: tuple[MarkerProfileSpec, ...] = (
    MarkerProfileSpec(
        name="javascript",
        markers=("package.json", ".js", ".mjs", ".cjs", "eslint.config.js"),
        required_any_markers=("package.json", ".js", ".mjs", ".cjs"),
    ),
    MarkerProfileSpec(
        name="typescript",
        markers=("tsconfig.json", ".ts", ".tsx", "eslint.config.ts"),
        required_any_markers=("tsconfig.json", ".ts", ".tsx"),
    ),
    MarkerProfileSpec(
        name="vue",
        markers=("vue.config.js", "vite.config.ts", ".vue", "src/App.vue"),
        required_any_markers=(".vue", "vue.config.js", "src/App.vue"),
        validation_commands=(
            SafeCommand(name="npm_test", command=("npm", "test")),
            SafeCommand(name="npm_lint", command=("npm", "run", "lint")),
        ),
    ),
    MarkerProfileSpec(
        name="nuxt",
        markers=("nuxt.config.ts", "nuxt.config.js", "app.vue", "pages/", "layouts/"),
        required_any_markers=("nuxt.config.ts", "nuxt.config.js"),
    ),
    MarkerProfileSpec(
        name="angular",
        markers=("angular.json", "src/app", ".component.ts", ".module.ts", "karma.conf.js"),
        required_any_markers=("angular.json",),
        validation_commands=(
            SafeCommand(name="ng_test", command=("npx", "ng", "test", "--watch=false")),
            SafeCommand(name="ng_lint", command=("npx", "ng", "lint")),
        ),
    ),
    MarkerProfileSpec(
        name="svelte",
        markers=("svelte.config.js", "svelte.config.ts", ".svelte", "src/routes"),
        required_any_markers=("svelte.config.js", "svelte.config.ts", ".svelte"),
    ),
    MarkerProfileSpec(
        name="sveltekit",
        markers=("svelte.config.js", "svelte.config.ts", "src/routes/+page.svelte"),
        required_any_markers=("src/routes/+page.svelte",),
    ),
    MarkerProfileSpec(
        name="astro",
        markers=("astro.config.mjs", "astro.config.ts", ".astro", "src/pages"),
        required_any_markers=("astro.config.mjs", "astro.config.ts"),
    ),
    MarkerProfileSpec(
        name="remix",
        markers=("remix.config.js", "app/routes", "app/root.tsx", "app/entry.server"),
        required_any_markers=("remix.config.js", "app/root.tsx"),
    ),
    MarkerProfileSpec(
        name="solid",
        markers=("solid.config.ts", "vite.config.ts", ".tsx", "src/routes"),
        required_any_markers=("solid.config.ts",),
    ),
    MarkerProfileSpec(
        name="ember",
        markers=("ember-cli-build.js", "app/routes", "app/components", "tests/acceptance"),
        required_any_markers=("ember-cli-build.js",),
    ),
    MarkerProfileSpec(
        name="electron",
        markers=("electron", "main.js", "preload.js", "electron-builder", "forge.config.js"),
        required_any_markers=("electron", "electron-builder", "forge.config.js"),
    ),
    MarkerProfileSpec(
        name="tauri",
        markers=("src-tauri/tauri.conf.json", "src-tauri/Cargo.toml", "tauri.conf.json"),
        required_any_markers=("src-tauri/tauri.conf.json", "src-tauri/Cargo.toml"),
    ),
    MarkerProfileSpec(
        name="react_native",
        markers=("react-native", "metro.config.js", "android/", "ios/", "App.tsx", "App.js"),
        required_any_markers=("react-native", "metro.config.js"),
    ),
    MarkerProfileSpec(
        name="expo",
        markers=("app.json", "app.config.js", "app.config.ts", "expo", "eas.json"),
        required_any_markers=("expo", "eas.json"),
    ),
    MarkerProfileSpec(
        name="ionic",
        markers=("ionic.config.json", "src/app", "capacitor.config.ts"),
        required_any_markers=("ionic.config.json",),
    ),
    MarkerProfileSpec(
        name="capacitor",
        markers=("capacitor.config.ts", "capacitor.config.json", "android/", "ios/"),
        required_any_markers=("capacitor.config.ts", "capacitor.config.json"),
    ),
    MarkerProfileSpec(
        name="flutter",
        markers=("pubspec.yaml", "lib/main.dart", "android/", "ios/", "test/"),
        required_any_markers=("pubspec.yaml", "lib/main.dart"),
        validation_commands=(
            SafeCommand(name="flutter_test", command=("flutter", "test")),
            SafeCommand(name="flutter_analyze", command=("flutter", "analyze")),
        ),
    ),
    MarkerProfileSpec(
        name="dart",
        markers=("pubspec.yaml", ".dart", "analysis_options.yaml"),
        required_any_markers=("pubspec.yaml", ".dart"),
    ),
    MarkerProfileSpec(
        name="android",
        markers=("AndroidManifest.xml", "build.gradle", "settings.gradle", "app/src/main"),
        required_any_markers=("AndroidManifest.xml", "app/src/main"),
    ),
    MarkerProfileSpec(
        name="ios",
        markers=(".xcodeproj", ".xcworkspace", "Podfile", "Info.plist", "Sources/"),
        required_any_markers=(".xcodeproj", ".xcworkspace", "Podfile"),
    ),
    MarkerProfileSpec(
        name="swift",
        markers=("Package.swift", ".swift", "Sources/", "Tests/"),
        required_any_markers=("Package.swift", ".swift"),
    ),
    MarkerProfileSpec(
        name="kotlin",
        markers=(".kt", "build.gradle.kts", "settings.gradle.kts", "src/main/kotlin"),
        required_any_markers=(".kt", "build.gradle.kts"),
    ),
    MarkerProfileSpec(
        name="kotlin_multiplatform",
        markers=("kotlin-multiplatform", "commonMain", "androidMain", "iosMain"),
        required_any_markers=("kotlin-multiplatform", "commonMain"),
    ),
    MarkerProfileSpec(
        name="express",
        markers=("express", "routes/", "app.js", "server.js", "controllers/"),
        required_any_markers=("express",),
    ),
    MarkerProfileSpec(
        name="nestjs",
        markers=("nest-cli.json", ".module.ts", ".controller.ts", ".service.ts"),
        required_any_markers=("nest-cli.json", ".module.ts"),
    ),
    MarkerProfileSpec(
        name="koa",
        markers=("koa", "routes/", "middleware/", "app.js"),
        required_any_markers=("koa",),
    ),
    MarkerProfileSpec(
        name="hapi",
        markers=("@hapi", "hapi", "server.js", "routes/"),
        required_any_markers=("@hapi", "hapi"),
    ),
    MarkerProfileSpec(
        name="adonis",
        markers=("adonisrc.ts", ".adonisrc.json", "start/routes.ts", "app/Controllers"),
        required_any_markers=("adonisrc.ts", ".adonisrc.json"),
    ),
    MarkerProfileSpec(
        name="php",
        markers=("composer.json", ".php", "phpunit.xml", "phpstan.neon"),
        required_any_markers=("composer.json", ".php"),
    ),
    MarkerProfileSpec(
        name="composer",
        markers=("composer.json", "composer.lock", "vendor/"),
        required_any_markers=("composer.json", "composer.lock"),
    ),
    MarkerProfileSpec(
        name="cakephp",
        markers=("config/app.php", "src/Controller", "src/Model", "cakephp"),
        required_any_markers=("cakephp",),
    ),
    MarkerProfileSpec(
        name="codeigniter",
        markers=("app/Config", "app/Controllers", "codeigniter", "system/CodeIgniter.php"),
        required_any_markers=("codeigniter", "system/CodeIgniter.php"),
    ),
    MarkerProfileSpec(
        name="yii",
        markers=("yii", "config/web.php", "controllers/", "models/"),
        required_any_markers=("yii", "config/web.php"),
    ),
    MarkerProfileSpec(
        name="magento",
        markers=("app/code", "app/etc/config.php", "Magento", "registration.php"),
        required_any_markers=("app/etc/config.php", "Magento"),
    ),
    MarkerProfileSpec(
        name="shopware",
        markers=("shopware", "custom/plugins", "src/Resources/config"),
        required_any_markers=("shopware",),
    ),
    MarkerProfileSpec(
        name="prestashop",
        markers=("prestashop", "modules/", "classes/", "controllers/"),
        required_any_markers=("prestashop",),
    ),
    MarkerProfileSpec(
        name="flask",
        markers=("flask", "app.py", "wsgi.py", "blueprints/", "templates/"),
        required_any_markers=("flask",),
    ),
    MarkerProfileSpec(
        name="celery",
        markers=("celery.py", "tasks.py", "celery_app.py", "beat_schedule"),
        required_any_markers=("celery.py", "celery_app.py"),
    ),
    MarkerProfileSpec(
        name="scrapy",
        markers=("scrapy.cfg", "spiders/", "items.py", "pipelines.py"),
        required_any_markers=("scrapy.cfg",),
    ),
    MarkerProfileSpec(
        name="airflow",
        markers=("airflow.cfg", "dags/", "plugins/", "Dockerfile.airflow"),
        required_any_markers=("airflow.cfg", "dags/"),
    ),
    MarkerProfileSpec(
        name="jupyter",
        markers=(".ipynb", "notebooks/", "jupyter", "environment.yml"),
        required_any_markers=(".ipynb", "notebooks/"),
    ),
    MarkerProfileSpec(
        name="maven",
        markers=("pom.xml", "src/main/java", "src/test/java"),
        required_any_markers=("pom.xml",),
        validation_commands=(SafeCommand(name="maven_test", command=("mvn", "test")),),
    ),
    MarkerProfileSpec(
        name="gradle",
        markers=("build.gradle", "build.gradle.kts", "settings.gradle", "gradlew"),
        required_any_markers=("build.gradle", "build.gradle.kts"),
        validation_commands=(SafeCommand(name="gradle_test", command=("./gradlew", "test")),),
    ),
    MarkerProfileSpec(
        name="quarkus",
        markers=("quarkus", "application.properties", "src/main/java"),
        required_any_markers=("quarkus",),
    ),
    MarkerProfileSpec(
        name="micronaut",
        markers=("micronaut", "application.yml", "src/main/java"),
        required_any_markers=("micronaut",),
    ),
    MarkerProfileSpec(
        name="jakarta_ee",
        markers=("jakarta", "WEB-INF", "persistence.xml", "src/main/java"),
        required_any_markers=("jakarta", "WEB-INF"),
    ),
    MarkerProfileSpec(
        name="aspnet",
        markers=(".csproj", "Program.cs", "Startup.cs", "Controllers/", "appsettings.json"),
        required_any_markers=(".csproj", "Controllers/"),
    ),
    MarkerProfileSpec(
        name="blazor",
        markers=(".razor", "_Imports.razor", "wwwroot/", "App.razor"),
        required_any_markers=(".razor", "App.razor"),
    ),
    MarkerProfileSpec(
        name="unity",
        markers=("Assets/", "ProjectSettings/", ".unity", ".asmdef"),
        required_any_markers=("ProjectSettings/", ".unity"),
    ),
    MarkerProfileSpec(
        name="cpp",
        markers=(".cpp", ".hpp", ".cc", ".h", "CMakeLists.txt"),
        required_any_markers=(".cpp", ".cc", "CMakeLists.txt"),
    ),
    MarkerProfileSpec(
        name="c",
        markers=(".c", ".h", "Makefile", "CMakeLists.txt"),
        required_any_markers=(".c",),
    ),
    MarkerProfileSpec(
        name="cmake",
        markers=("CMakeLists.txt", "cmake/", ".cmake"),
        required_any_markers=("CMakeLists.txt",),
    ),
    MarkerProfileSpec(
        name="make",
        markers=("Makefile", "makefile", ".mk"),
        required_any_markers=("Makefile", "makefile"),
    ),
    MarkerProfileSpec(
        name="bazel",
        markers=("WORKSPACE", "WORKSPACE.bazel", "BUILD", "BUILD.bazel", ".bzl"),
        required_any_markers=("WORKSPACE", "WORKSPACE.bazel", "BUILD.bazel"),
    ),
    MarkerProfileSpec(
        name="pants",
        markers=("pants.toml", "BUILD", "3rdparty/"),
        required_any_markers=("pants.toml",),
    ),
    MarkerProfileSpec(
        name="scala",
        markers=("build.sbt", ".scala", "project/plugins.sbt"),
        required_any_markers=("build.sbt", ".scala"),
    ),
    MarkerProfileSpec(
        name="elixir",
        markers=("mix.exs", ".ex", ".exs", "lib/", "test/"),
        required_any_markers=("mix.exs",),
    ),
    MarkerProfileSpec(
        name="phoenix",
        markers=("mix.exs", "lib/*_web", "assets/", "config/dev.exs"),
        required_any_markers=("lib/*_web", "config/dev.exs"),
    ),
    MarkerProfileSpec(
        name="erlang",
        markers=("rebar.config", ".erl", ".hrl", "src/"),
        required_any_markers=("rebar.config", ".erl"),
    ),
    MarkerProfileSpec(
        name="clojure",
        markers=("deps.edn", "project.clj", ".clj", ".cljs"),
        required_any_markers=("deps.edn", "project.clj", ".clj"),
    ),
    MarkerProfileSpec(
        name="haskell",
        markers=("stack.yaml", ".cabal", "cabal.project", ".hs"),
        required_any_markers=("stack.yaml", ".cabal", "cabal.project"),
    ),
    MarkerProfileSpec(
        name="ocaml",
        markers=("dune-project", "dune", ".ml", ".mli"),
        required_any_markers=("dune-project", ".ml"),
    ),
    MarkerProfileSpec(
        name="fsharp",
        markers=(".fsproj", ".fs", ".fsx", "paket.dependencies"),
        required_any_markers=(".fsproj", ".fs"),
    ),
    MarkerProfileSpec(
        name="ruby",
        markers=("Gemfile", ".rb", ".gemspec", "Rakefile"),
        required_any_markers=("Gemfile", ".gemspec", ".rb"),
    ),
    MarkerProfileSpec(
        name="r",
        markers=(".Rproj", ".R", "DESCRIPTION", "renv.lock"),
        required_any_markers=(".Rproj", "renv.lock"),
    ),
    MarkerProfileSpec(
        name="julia",
        markers=("Project.toml", "Manifest.toml", ".jl", "src/"),
        required_any_markers=(".jl",),
    ),
    MarkerProfileSpec(
        name="matlab",
        markers=(".m", ".mlx", "matlab.prj"),
        required_any_markers=("matlab.prj",),
    ),
    MarkerProfileSpec(
        name="lua",
        markers=(".lua", "rockspec", ".luacheckrc"),
        required_any_markers=("rockspec", ".lua"),
    ),
    MarkerProfileSpec(
        name="docker",
        markers=("Dockerfile", "docker-compose.yml", "compose.yaml", ".dockerignore"),
        required_any_markers=("Dockerfile", "docker-compose.yml", "compose.yaml"),
    ),
    MarkerProfileSpec(
        name="kubernetes",
        markers=("kustomization.yaml", "deployment.yaml", "service.yaml", "ingress.yaml"),
        required_any_markers=("kustomization.yaml", "deployment.yaml"),
    ),
    MarkerProfileSpec(
        name="helm",
        markers=("Chart.yaml", "values.yaml", "templates/deployment.yaml"),
        required_any_markers=("Chart.yaml",),
    ),
    MarkerProfileSpec(
        name="ansible",
        markers=("ansible.cfg", "playbook.yml", "roles/", "inventory/"),
        required_any_markers=("ansible.cfg", "playbook.yml"),
    ),
    MarkerProfileSpec(
        name="pulumi",
        markers=("Pulumi.yaml", "Pulumi.dev.yaml", "index.ts", "__main__.py"),
        required_any_markers=("Pulumi.yaml",),
    ),
    MarkerProfileSpec(
        name="cloudformation",
        markers=("template.yaml", "template.yml", "AWS::", "cloudformation"),
        required_any_markers=("cloudformation",),
    ),
    MarkerProfileSpec(
        name="serverless",
        markers=("serverless.yml", "serverless.yaml", "functions:", "serverless.ts"),
        required_any_markers=("serverless.yml", "serverless.yaml", "serverless.ts"),
    ),
    MarkerProfileSpec(
        name="aws_sam",
        markers=("template.yaml", "samconfig.toml", "AWS::Serverless"),
        required_any_markers=("samconfig.toml", "AWS::Serverless"),
    ),
    MarkerProfileSpec(
        name="github_actions",
        markers=(".github/workflows", "action.yml", "action.yaml"),
        required_any_markers=(".github/workflows", "action.yml", "action.yaml"),
    ),
    MarkerProfileSpec(
        name="gitlab_ci",
        markers=(".gitlab-ci.yml", ".gitlab/ci"),
        required_any_markers=(".gitlab-ci.yml",),
    ),
    MarkerProfileSpec(
        name="azure_devops",
        markers=("azure-pipelines.yml", ".azure-pipelines"),
        required_any_markers=("azure-pipelines.yml",),
    ),
    MarkerProfileSpec(
        name="nix",
        markers=("flake.nix", "default.nix", "shell.nix"),
        required_any_markers=("flake.nix", "default.nix", "shell.nix"),
    ),
    MarkerProfileSpec(
        name="packer",
        markers=(".pkr.hcl", "packer.json"),
        required_any_markers=(".pkr.hcl", "packer.json"),
    ),
    MarkerProfileSpec(
        name="nomad",
        markers=(".nomad", ".nomad.hcl"),
        required_any_markers=(".nomad", ".nomad.hcl"),
    ),
    MarkerProfileSpec(
        name="dbt",
        markers=("dbt_project.yml", "models/", "macros/", "profiles.yml"),
        required_any_markers=("dbt_project.yml",),
    ),
    MarkerProfileSpec(
        name="spark",
        markers=("spark", "pyspark", "spark-submit", "build.sbt"),
        required_any_markers=("spark", "pyspark", "spark-submit"),
    ),
    MarkerProfileSpec(
        name="dagster",
        markers=("dagster.yaml", "workspace.yaml", "definitions.py"),
        required_any_markers=("dagster.yaml", "workspace.yaml"),
    ),
    MarkerProfileSpec(
        name="prefect",
        markers=("prefect.yaml", "flows/", "deployments/"),
        required_any_markers=("prefect.yaml",),
    ),
    MarkerProfileSpec(
        name="great_expectations",
        markers=("great_expectations.yml", "expectations/", "checkpoints/"),
        required_any_markers=("great_expectations.yml",),
    ),
    MarkerProfileSpec(
        name="dvc",
        markers=("dvc.yaml", ".dvc", ".dvcignore"),
        required_any_markers=("dvc.yaml", ".dvc"),
    ),
    MarkerProfileSpec(
        name="mlflow",
        markers=("MLproject", "mlruns/", "mlflow"),
        required_any_markers=("MLproject", "mlruns/"),
    ),
    MarkerProfileSpec(
        name="prisma",
        markers=("schema.prisma", "prisma/", "@prisma"),
        required_any_markers=("schema.prisma", "prisma/"),
    ),
    MarkerProfileSpec(
        name="supabase",
        markers=("supabase/config.toml", "supabase/migrations", "supabase/functions"),
        required_any_markers=("supabase/config.toml",),
    ),
    MarkerProfileSpec(
        name="hasura",
        markers=("metadata/databases", "hasura", "migrations/"),
        required_any_markers=("hasura", "metadata/databases"),
    ),
    MarkerProfileSpec(
        name="sql",
        markers=(".sql", "migrations/", "schema.sql", "seeds/"),
        required_any_markers=(".sql", "schema.sql"),
    ),
    MarkerProfileSpec(
        name="nx",
        markers=("nx.json", "workspace.json", "project.json"),
        required_any_markers=("nx.json",),
    ),
    MarkerProfileSpec(
        name="turborepo",
        markers=("turbo.json", "packages/", "apps/"),
        required_any_markers=("turbo.json",),
    ),
    MarkerProfileSpec(
        name="pnpm_workspace",
        markers=("pnpm-workspace.yaml", "packages/", "apps/"),
        required_any_markers=("pnpm-workspace.yaml",),
    ),
    MarkerProfileSpec(
        name="poetry",
        markers=("pyproject.toml", "poetry.lock", "tool.poetry"),
        required_any_markers=("poetry.lock",),
    ),
    MarkerProfileSpec(
        name="hugo",
        markers=("hugo.toml", "hugo.yaml", "config.toml", "content/", "layouts/"),
        required_any_markers=("hugo.toml", "hugo.yaml"),
    ),
    MarkerProfileSpec(
        name="jekyll",
        markers=("_config.yml", "_posts/", "_layouts/", "Gemfile"),
        required_any_markers=("_config.yml", "_posts/"),
    ),
    MarkerProfileSpec(
        name="eleventy",
        markers=(".eleventy.js", "eleventy.config.js", "_includes/"),
        required_any_markers=(".eleventy.js", "eleventy.config.js"),
    ),
    MarkerProfileSpec(
        name="shopify",
        markers=("shopify.theme.toml", "templates/", "sections/", "snippets/", ".liquid"),
        required_any_markers=("shopify.theme.toml", ".liquid"),
    ),
    MarkerProfileSpec(
        name="salesforce",
        markers=("sfdx-project.json", "force-app/", "manifest/package.xml"),
        required_any_markers=("sfdx-project.json",),
    ),
    MarkerProfileSpec(
        name="deno",
        markers=("deno.json", "deno.jsonc", "fresh.config.ts", "main.ts"),
        required_any_markers=("deno.json", "deno.jsonc"),
    ),
    MarkerProfileSpec(
        name="bun",
        markers=("bun.lockb", "bun.lock", "bunfig.toml"),
        required_any_markers=("bun.lockb", "bun.lock", "bunfig.toml"),
    ),
    MarkerProfileSpec(
        name="vite",
        markers=("vite.config.ts", "vite.config.js", "vite.config.mjs"),
        required_any_markers=("vite.config.ts", "vite.config.js", "vite.config.mjs"),
    ),
    MarkerProfileSpec(
        name="webpack",
        markers=("webpack.config.js", "webpack.config.ts", "webpack.config.mjs"),
        required_any_markers=("webpack.config.js", "webpack.config.ts", "webpack.config.mjs"),
    ),
    MarkerProfileSpec(
        name="rollup",
        markers=("rollup.config.js", "rollup.config.ts", "rollup.config.mjs"),
        required_any_markers=("rollup.config.js", "rollup.config.ts", "rollup.config.mjs"),
    ),
    MarkerProfileSpec(
        name="parcel",
        markers=(".parcelrc", "parcel.config.js"),
        required_any_markers=(".parcelrc", "parcel.config.js"),
    ),
    MarkerProfileSpec(
        name="storybook",
        markers=(".storybook/", "storybook.config.ts", "main.stories.tsx"),
        required_any_markers=(".storybook/", "storybook.config.ts"),
    ),
    MarkerProfileSpec(
        name="jest",
        markers=("jest.config.js", "jest.config.ts", "__tests__/", ".spec.ts", ".test.ts"),
        required_any_markers=("jest.config.js", "jest.config.ts"),
    ),
    MarkerProfileSpec(
        name="vitest",
        markers=("vitest.config.ts", "vitest.config.js", ".test.ts", ".spec.ts"),
        required_any_markers=("vitest.config.ts", "vitest.config.js"),
    ),
    MarkerProfileSpec(
        name="cypress",
        markers=("cypress.config.ts", "cypress.config.js", "cypress/e2e"),
        required_any_markers=("cypress.config.ts", "cypress.config.js", "cypress/e2e"),
    ),
    MarkerProfileSpec(
        name="playwright",
        markers=("playwright.config.ts", "playwright.config.js", "tests/e2e"),
        required_any_markers=("playwright.config.ts", "playwright.config.js"),
    ),
    MarkerProfileSpec(
        name="qwik",
        markers=("qwik.config.ts", "src/routes", "src/root.tsx"),
        required_any_markers=("qwik.config.ts",),
    ),
    MarkerProfileSpec(
        name="redwood",
        markers=("redwood.toml", "api/src", "web/src"),
        required_any_markers=("redwood.toml",),
    ),
    MarkerProfileSpec(
        name="blitz",
        markers=("blitz.config.ts", "blitz.config.js", "app/"),
        required_any_markers=("blitz.config.ts", "blitz.config.js"),
    ),
    MarkerProfileSpec(
        name="meteor",
        markers=(".meteor/", ".meteor/packages", ".meteor/release"),
        required_any_markers=(".meteor/", ".meteor/packages"),
    ),
    MarkerProfileSpec(
        name="gatsby",
        markers=("gatsby-config.js", "gatsby-node.js", "gatsby-browser.js"),
        required_any_markers=("gatsby-config.js",),
    ),
    MarkerProfileSpec(
        name="docusaurus",
        markers=("docusaurus.config.js", "docusaurus.config.ts", "sidebars.js"),
        required_any_markers=("docusaurus.config.js", "docusaurus.config.ts"),
    ),
    MarkerProfileSpec(
        name="vitepress",
        markers=(".vitepress/config.ts", ".vitepress/config.js"),
        required_any_markers=(".vitepress/config.ts", ".vitepress/config.js"),
    ),
    MarkerProfileSpec(
        name="mkdocs",
        markers=("mkdocs.yml", "mkdocs.yaml", "docs/"),
        required_any_markers=("mkdocs.yml", "mkdocs.yaml"),
    ),
    MarkerProfileSpec(
        name="sphinx",
        markers=("conf.py", "index.rst", "docs/conf.py"),
        required_any_markers=("docs/conf.py",),
    ),
    MarkerProfileSpec(
        name="mdbook",
        markers=("book.toml", "src/SUMMARY.md"),
        required_any_markers=("book.toml",),
    ),
    MarkerProfileSpec(
        name="asciidoc",
        markers=(".adoc", ".asciidoc", "antora.yml"),
        required_any_markers=(".adoc", ".asciidoc", "antora.yml"),
    ),
    MarkerProfileSpec(
        name="openapi",
        markers=("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml"),
        required_any_markers=("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml"),
    ),
    MarkerProfileSpec(
        name="graphql",
        markers=(".graphql", ".gql", "schema.graphql", "graphql.config.yml"),
        required_any_markers=(".graphql", ".gql", "schema.graphql", "graphql.config.yml"),
    ),
    MarkerProfileSpec(
        name="apollo",
        markers=("apollo.config.js", "apollo.config.ts", "schema.graphql"),
        required_any_markers=("apollo.config.js", "apollo.config.ts"),
    ),
    MarkerProfileSpec(
        name="grpc",
        markers=(".proto", "buf.yaml", "grpc"),
        required_any_markers=(".proto", "buf.yaml"),
    ),
    MarkerProfileSpec(
        name="protobuf",
        markers=(".proto", "buf.yaml", "buf.gen.yaml"),
        required_any_markers=(".proto", "buf.yaml"),
    ),
    MarkerProfileSpec(
        name="strapi",
        markers=("config/plugins.js", "src/api/", "strapi-server.js", ".strapi"),
        required_any_markers=(".strapi", "strapi-server.js"),
    ),
    MarkerProfileSpec(
        name="directus",
        markers=("directus", "extensions/", "directus.config.js"),
        required_any_markers=("directus.config.js",),
    ),
    MarkerProfileSpec(
        name="payload_cms",
        markers=("payload.config.ts", "payload.config.js", "collections/"),
        required_any_markers=("payload.config.ts", "payload.config.js"),
    ),
    MarkerProfileSpec(
        name="keystone",
        markers=("keystone.ts", "keystone.js", "schema.ts"),
        required_any_markers=("keystone.ts", "keystone.js"),
    ),
    MarkerProfileSpec(
        name="sanity",
        markers=("sanity.config.ts", "sanity.cli.ts", "schemas/"),
        required_any_markers=("sanity.config.ts", "sanity.cli.ts"),
    ),
    MarkerProfileSpec(
        name="typo3",
        markers=("typo3conf/", "ext_emconf.php", "Configuration/TCA"),
        required_any_markers=("typo3conf/", "ext_emconf.php"),
    ),
    MarkerProfileSpec(
        name="joomla",
        markers=("joomla", "configuration.php", "administrator/manifests"),
        required_any_markers=("administrator/manifests",),
    ),
    MarkerProfileSpec(
        name="ghost",
        markers=("ghost", "content/themes", "routes.yaml"),
        required_any_markers=("content/themes",),
    ),
    MarkerProfileSpec(
        name="netlify",
        markers=("netlify.toml", ".netlify/"),
        required_any_markers=("netlify.toml",),
    ),
    MarkerProfileSpec(
        name="vercel",
        markers=("vercel.json", ".vercel/"),
        required_any_markers=("vercel.json",),
    ),
    MarkerProfileSpec(
        name="firebase",
        markers=("firebase.json", ".firebaserc", "firestore.rules"),
        required_any_markers=("firebase.json", ".firebaserc"),
    ),
    MarkerProfileSpec(
        name="cloudflare_workers",
        markers=("wrangler.toml", "wrangler.json", "worker.ts", "worker.js"),
        required_any_markers=("wrangler.toml", "wrangler.json"),
    ),
    MarkerProfileSpec(
        name="aws_cdk",
        markers=("cdk.json", "lib/*-stack.ts", "bin/", "constructs/"),
        required_any_markers=("cdk.json",),
    ),
    MarkerProfileSpec(
        name="cdk8s",
        markers=("cdk8s.yaml", "imports/k8s.ts", "main.ts"),
        required_any_markers=("cdk8s.yaml",),
    ),
    MarkerProfileSpec(
        name="cdktf",
        markers=("cdktf.json", "main.ts", "main.py"),
        required_any_markers=("cdktf.json",),
    ),
    MarkerProfileSpec(
        name="terragrunt",
        markers=("terragrunt.hcl", "terragrunt-cache"),
        required_any_markers=("terragrunt.hcl",),
    ),
    MarkerProfileSpec(
        name="opentofu",
        markers=(".tofu", ".tofu.lock.hcl", "tofu"),
        required_any_markers=(".tofu.lock.hcl", ".tofu"),
    ),
    MarkerProfileSpec(
        name="bicep",
        markers=(".bicep", "main.bicep", "azuredeploy.json"),
        required_any_markers=(".bicep", "main.bicep"),
    ),
    MarkerProfileSpec(
        name="crossplane",
        markers=("crossplane.yaml", "composition.yaml", "CompositeResourceDefinition"),
        required_any_markers=("crossplane.yaml", "composition.yaml"),
    ),
    MarkerProfileSpec(
        name="argocd",
        markers=("argocd", "Application.yaml", "applicationset.yaml"),
        required_any_markers=("argocd", "applicationset.yaml"),
    ),
    MarkerProfileSpec(
        name="fluxcd",
        markers=("flux-system/", "kustomization.yaml", "helmrelease.yaml"),
        required_any_markers=("flux-system/", "helmrelease.yaml"),
    ),
    MarkerProfileSpec(
        name="tekton",
        markers=("TaskRun", "PipelineRun", "tekton.dev", ".tekton/"),
        required_any_markers=(".tekton/",),
    ),
    MarkerProfileSpec(
        name="jenkins",
        markers=("Jenkinsfile", ".jenkins/"),
        required_any_markers=("Jenkinsfile",),
    ),
    MarkerProfileSpec(
        name="circleci",
        markers=(".circleci/config.yml", ".circleci/config.yaml"),
        required_any_markers=(".circleci/config.yml", ".circleci/config.yaml"),
    ),
    MarkerProfileSpec(
        name="buildkite",
        markers=(".buildkite/pipeline.yml", ".buildkite/pipeline.yaml"),
        required_any_markers=(".buildkite/pipeline.yml", ".buildkite/pipeline.yaml"),
    ),
    MarkerProfileSpec(
        name="drone_ci",
        markers=(".drone.yml", ".drone.yaml"),
        required_any_markers=(".drone.yml", ".drone.yaml"),
    ),
    MarkerProfileSpec(
        name="woodpecker_ci",
        markers=(".woodpecker.yml", ".woodpecker.yaml", ".woodpecker/"),
        required_any_markers=(".woodpecker.yml", ".woodpecker.yaml", ".woodpecker/"),
    ),
    MarkerProfileSpec(
        name="dependabot",
        markers=(".github/dependabot.yml", ".github/dependabot.yaml"),
        required_any_markers=(".github/dependabot.yml", ".github/dependabot.yaml"),
    ),
    MarkerProfileSpec(
        name="renovate",
        markers=("renovate.json", ".renovaterc", ".github/renovate.json"),
        required_any_markers=("renovate.json", ".renovaterc", ".github/renovate.json"),
    ),
    MarkerProfileSpec(
        name="pre_commit",
        markers=(".pre-commit-config.yaml", ".pre-commit-hooks.yaml"),
        required_any_markers=(".pre-commit-config.yaml",),
    ),
    MarkerProfileSpec(
        name="semgrep",
        markers=(".semgrep.yml", ".semgrep.yaml", "semgrep.yml"),
        required_any_markers=(".semgrep.yml", ".semgrep.yaml", "semgrep.yml"),
    ),
    MarkerProfileSpec(
        name="trivy",
        markers=("trivy.yaml", "trivy.yml", ".trivyignore"),
        required_any_markers=("trivy.yaml", "trivy.yml", ".trivyignore"),
    ),
    MarkerProfileSpec(
        name="checkov",
        markers=(".checkov.yml", ".checkov.yaml", "checkov.yaml"),
        required_any_markers=(".checkov.yml", ".checkov.yaml", "checkov.yaml"),
    ),
    MarkerProfileSpec(
        name="snyk",
        markers=(".snyk", "snyk.yaml"),
        required_any_markers=(".snyk", "snyk.yaml"),
    ),
    MarkerProfileSpec(
        name="opa",
        markers=(".rego", "policy.rego", "opa.yaml"),
        required_any_markers=(".rego", "policy.rego"),
    ),
    MarkerProfileSpec(
        name="prometheus",
        markers=("prometheus.yml", "prometheus.yaml", "alert.rules.yml"),
        required_any_markers=("prometheus.yml", "prometheus.yaml"),
    ),
    MarkerProfileSpec(
        name="grafana",
        markers=("grafana.ini", "dashboards/", "provisioning/dashboards"),
        required_any_markers=("grafana.ini", "provisioning/dashboards"),
    ),
    MarkerProfileSpec(
        name="opentelemetry",
        markers=("otelcol.yaml", "otel-collector-config.yaml", "opentelemetry"),
        required_any_markers=("otelcol.yaml", "otel-collector-config.yaml"),
    ),
    MarkerProfileSpec(
        name="elasticsearch",
        markers=("elasticsearch.yml", "logstash.conf", "kibana.yml"),
        required_any_markers=("elasticsearch.yml",),
    ),
    MarkerProfileSpec(
        name="opensearch",
        markers=("opensearch.yml", "opensearch_dashboards.yml"),
        required_any_markers=("opensearch.yml",),
    ),
    MarkerProfileSpec(
        name="kafka",
        markers=("server.properties", "kafka", "docker-compose.kafka.yml"),
        required_any_markers=("docker-compose.kafka.yml",),
    ),
    MarkerProfileSpec(
        name="flink",
        markers=("flink-conf.yaml", "flink", "src/main/java"),
        required_any_markers=("flink-conf.yaml",),
    ),
    MarkerProfileSpec(
        name="beam",
        markers=("apache_beam", "beam.yaml", "DataflowPipelineOptions"),
        required_any_markers=("beam.yaml", "apache_beam"),
    ),
    MarkerProfileSpec(
        name="trino",
        markers=("etc/catalog", "trino", "config.properties"),
        required_any_markers=("trino",),
    ),
    MarkerProfileSpec(
        name="snowflake",
        markers=("snowflake.yml", "snowflake.yaml", "snowpark"),
        required_any_markers=("snowflake.yml", "snowflake.yaml"),
    ),
    MarkerProfileSpec(
        name="bigquery",
        markers=("bigquery", "bq", "Dataform"),
        required_any_markers=("Dataform",),
    ),
    MarkerProfileSpec(
        name="redshift",
        markers=("redshift", "redshift.sql"),
        required_any_markers=("redshift.sql",),
    ),
    MarkerProfileSpec(
        name="alembic",
        markers=("alembic.ini", "versions/", "env.py"),
        required_any_markers=("alembic.ini",),
    ),
    MarkerProfileSpec(
        name="flyway",
        markers=("flyway.conf", "sql/V", "db/migration"),
        required_any_markers=("flyway.conf", "db/migration"),
    ),
    MarkerProfileSpec(
        name="liquibase",
        markers=("liquibase.properties", "changelog.xml", "db.changelog"),
        required_any_markers=("liquibase.properties", "changelog.xml"),
    ),
    MarkerProfileSpec(
        name="gin",
        markers=("gin-gonic", "gin.Context", "go.mod"),
        required_any_markers=("gin-gonic",),
    ),
    MarkerProfileSpec(
        name="echo_go",
        markers=("labstack/echo", "echo.Context", "go.mod"),
        required_any_markers=("labstack/echo",),
    ),
    MarkerProfileSpec(
        name="fiber_go",
        markers=("gofiber", "fiber.Ctx", "go.mod"),
        required_any_markers=("gofiber",),
    ),
    MarkerProfileSpec(
        name="chi_go",
        markers=("go-chi", "chi.Router", "go.mod"),
        required_any_markers=("go-chi",),
    ),
    MarkerProfileSpec(
        name="actix",
        markers=("actix-web", "Cargo.toml", "src/main.rs"),
        required_any_markers=("actix-web",),
    ),
    MarkerProfileSpec(
        name="axum",
        markers=("axum", "Cargo.toml", "src/main.rs"),
        required_any_markers=("axum",),
    ),
    MarkerProfileSpec(
        name="rocket",
        markers=("rocket", "Rocket.toml", "Cargo.toml"),
        required_any_markers=("Rocket.toml",),
    ),
    MarkerProfileSpec(
        name="bevy",
        markers=("bevy", "Cargo.toml", "assets/"),
        required_any_markers=("bevy",),
    ),
    MarkerProfileSpec(
        name="godot",
        markers=("project.godot", ".gd", ".tscn"),
        required_any_markers=("project.godot",),
    ),
    MarkerProfileSpec(
        name="unreal",
        markers=(".uproject", ".uplugin", "Source/", "Content/"),
        required_any_markers=(".uproject",),
    ),
    MarkerProfileSpec(
        name="solidity",
        markers=(".sol", "contracts/", "hardhat.config.ts", "foundry.toml"),
        required_any_markers=(".sol", "hardhat.config.ts", "foundry.toml"),
    ),
    MarkerProfileSpec(
        name="hardhat",
        markers=("hardhat.config.ts", "hardhat.config.js", "contracts/"),
        required_any_markers=("hardhat.config.ts", "hardhat.config.js"),
    ),
    MarkerProfileSpec(
        name="foundry",
        markers=("foundry.toml", "src/", "script/", "test/"),
        required_any_markers=("foundry.toml",),
    ),
    MarkerProfileSpec(
        name="truffle",
        markers=("truffle-config.js", "truffle.js", "migrations/"),
        required_any_markers=("truffle-config.js", "truffle.js"),
    ),
    MarkerProfileSpec(
        name="anchor",
        markers=("Anchor.toml", "programs/", "migrations/"),
        required_any_markers=("Anchor.toml",),
    ),
    MarkerProfileSpec(
        name="move",
        markers=("Move.toml", ".move", "sources/"),
        required_any_markers=("Move.toml",),
    ),
    MarkerProfileSpec(
        name="cosmos_sdk",
        markers=("cosmossdk.io", "x/", "app.go"),
        required_any_markers=("cosmossdk.io",),
    ),
    MarkerProfileSpec(
        name="substrate",
        markers=("pallets/", "runtime/", "substrate", "Cargo.toml"),
        required_any_markers=("pallets/", "substrate"),
    ),
    MarkerProfileSpec(
        name="conda",
        markers=("environment.yml", "environment.yaml", "conda-lock.yml"),
        required_any_markers=("environment.yml", "environment.yaml", "conda-lock.yml"),
    ),
    MarkerProfileSpec(
        name="pipenv",
        markers=("Pipfile", "Pipfile.lock"),
        required_any_markers=("Pipfile",),
    ),
    MarkerProfileSpec(
        name="tox",
        markers=("tox.ini", ".tox/"),
        required_any_markers=("tox.ini",),
    ),
    MarkerProfileSpec(
        name="nox",
        markers=("noxfile.py", ".nox/"),
        required_any_markers=("noxfile.py",),
    ),
    MarkerProfileSpec(
        name="hatch",
        markers=("hatch.toml", "pyproject.toml", "hatch_build.py"),
        required_any_markers=("hatch.toml", "hatch_build.py"),
    ),
    MarkerProfileSpec(
        name="uv",
        markers=("uv.lock", "pyproject.toml"),
        required_any_markers=("uv.lock",),
    ),
    MarkerProfileSpec(
        name="meson",
        markers=("meson.build", "meson_options.txt"),
        required_any_markers=("meson.build",),
    ),
    MarkerProfileSpec(
        name="ninja",
        markers=("build.ninja", ".ninja_log"),
        required_any_markers=("build.ninja",),
    ),
    MarkerProfileSpec(
        name="arduino",
        markers=(".ino", "library.properties", "sketch.yaml"),
        required_any_markers=(".ino", "sketch.yaml"),
    ),
    MarkerProfileSpec(
        name="platformio",
        markers=("platformio.ini", "src/main.cpp", "lib/"),
        required_any_markers=("platformio.ini",),
    ),
    MarkerProfileSpec(
        name="zephyr",
        markers=("west.yml", "prj.conf", "zephyr", "CMakeLists.txt"),
        required_any_markers=("west.yml", "prj.conf"),
    ),
    MarkerProfileSpec(
        name="langchain",
        markers=("langchain", "langchain.json", "chains/"),
        required_any_markers=("langchain.json",),
    ),
    MarkerProfileSpec(
        name="llamaindex",
        markers=("llama_index", "llama-index", "indices/"),
        required_any_markers=("llama_index", "llama-index"),
    ),
    MarkerProfileSpec(
        name="haystack",
        markers=("haystack", "pipelines.yaml", "document_store"),
        required_any_markers=("pipelines.yaml",),
    ),
    MarkerProfileSpec(
        name="semantic_kernel",
        markers=("semantic-kernel", "skprompt.txt", "plugins/"),
        required_any_markers=("skprompt.txt",),
    ),
    MarkerProfileSpec(
        name="crewai",
        markers=("crewai", "agents.yaml", "tasks.yaml"),
        required_any_markers=("agents.yaml", "tasks.yaml"),
    ),
    MarkerProfileSpec(
        name="autogen",
        markers=("autogen", "agentchat", "groupchat"),
        required_any_markers=("autogen",),
    ),
    MarkerProfileSpec(
        name="ray",
        markers=("ray", "ray_cluster.yaml", "serve_config.yaml"),
        required_any_markers=("ray_cluster.yaml", "serve_config.yaml"),
    ),
    MarkerProfileSpec(
        name="kedro",
        markers=("conf/base/catalog.yml", "parameters.yml", "pipeline_registry.py"),
        required_any_markers=("conf/base/catalog.yml", "pipeline_registry.py"),
    ),
    MarkerProfileSpec(
        name="bentoml",
        markers=("bentofile.yaml", "bentoml_configuration.yaml", "service.py"),
        required_any_markers=("bentofile.yaml", "bentoml_configuration.yaml"),
    ),
    MarkerProfileSpec(
        name="feast",
        markers=("feature_store.yaml", "feature_repo/", "entities.py", "features.py"),
        required_any_markers=("feature_store.yaml",),
    ),
)


def _matches_marker(path: str, marker: str) -> bool:
    normalized_path = path.lower()
    normalized_marker = marker.lower()
    if normalized_marker.startswith("."):
        return normalized_path.endswith(normalized_marker)
    if normalized_marker.endswith("/"):
        return (
            normalized_path.startswith(normalized_marker)
            or f"/{normalized_marker}" in normalized_path
        )
    return normalized_marker in normalized_path or normalized_path.endswith(normalized_marker)


def _discover_paths(project_root: Path) -> list[str]:
    if not project_root.exists():
        return []
    paths: list[str] = []
    for path in project_root.rglob("*"):
        if path.is_file():
            paths.append(path.relative_to(project_root).as_posix())
    return paths
