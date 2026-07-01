"""Tests for sdk-developer-platform (PR-R2-E).

REQ-sdk-dev-001..005 — `opencontext-sdk` package surface.
"""

from __future__ import annotations

import json
from pathlib import Path


class TestSdkPlatform:
    def test_scaffold_kind_enumeration(self) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        kinds = platform.scaffold_kinds()
        # 8 scaffold kinds per REQ-sdk-dev-002
        assert set(kinds) == {
            "plugin",
            "skill",
            "harness",
            "provider",
            "studio-panel",
            "recipe",
            "command",
            "profile",
        }

    def test_create_plugin_template_renders_8_files(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        out_dir = tmp_path / "hello-oc"
        files = platform.create_plugin_template("hello-oc", out_dir)

        expected = {
            "hello_oc/__init__.py",
            "plugin.yaml",
            "tests/test_hello_oc.py",
            "docs/README.md",
            "CHANGELOG.md",
            ".github/workflows/test.yml",
            "scripts/test.sh",
            "conformance/conftest.py",
        }
        assert expected.issubset(set(files))
        # All files exist on disk
        for rel in expected:
            assert (out_dir / rel).exists()

    def test_create_plugin_template_deterministic(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        a = platform.create_plugin_template("alpha", tmp_path / "a")
        b = platform.create_plugin_template("alpha", tmp_path / "b")
        for rel in a:
            assert Path(b[rel]).read_bytes() == Path(a[rel]).read_bytes()

    def test_validate_plugin_passing(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        out_dir = tmp_path / "p"
        platform.create_plugin_template("p", out_dir)
        result = platform.validate_plugin(out_dir)
        assert result["status"] == "ok"
        assert result["errors"] == []

    def test_validate_plugin_missing_permissions(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        out_dir = tmp_path / "bad"
        platform.create_plugin_template("bad", out_dir)
        # Strip permissions to simulate the spec's missing-field scenario
        manifest = out_dir / "plugin.yaml"
        text = manifest.read_text()
        cleaned = "\n".join(
            line for line in text.splitlines() if "permissions" not in line
        )
        manifest.write_text(cleaned)
        result = platform.validate_plugin(out_dir)
        assert result["status"] == "error"
        assert any("permissions" in e for e in result["errors"])

    def test_publish_plugin_writes_receipt(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        out_dir = tmp_path / "publishable"
        platform.create_plugin_template("publishable", out_dir)
        receipt = platform.publish_plugin(out_dir, registry="local")
        assert receipt["plugin"] == "publishable"
        assert receipt["registry"] == "local"
        assert receipt["status"] == "published"
        # Receipt must contain a manifest hash + version
        assert "manifest_hash" in receipt
        assert "version" in receipt

    def test_compat_check(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        result = platform.compat_check(
            sdk_min_version="1.0.0",
            sdk_max_version="2.0.0",
            runtime_version="1.4.0",
        )
        assert result["status"] == "ok"
        # Mismatch path
        bad = platform.compat_check(
            sdk_min_version="2.0.0",
            sdk_max_version="3.0.0",
            runtime_version="1.4.0",
        )
        assert bad["status"] == "fail"

    def test_publish_receipt_round_trip(self, tmp_path: Path) -> None:
        from opencontext_core.sdk.platform import SdkPlatform

        platform = SdkPlatform()
        out_dir = tmp_path / "p2"
        platform.create_plugin_template("p2", out_dir)
        receipt = platform.publish_plugin(out_dir, registry="local")
        # Receipt is JSON-serializable
        encoded = json.dumps(receipt, sort_keys=True)
        decoded = json.loads(encoded)
        assert decoded == receipt
