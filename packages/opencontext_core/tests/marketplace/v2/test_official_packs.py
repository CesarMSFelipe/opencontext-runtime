"""REQ-mkt-v1-004: 3 official packs load + pass."""

from __future__ import annotations

from opencontext_core.marketplace.v2.official_packs import (
    OFFICIAL_PACK_IDS,
    all_packs,
    get_pack,
)


def test_REQ_mkt_v1_004_three_packs_registered() -> None:
    assert set(OFFICIAL_PACK_IDS) >= {
        "python-pytest", "typescript-eslint", "php-phpunit",
    }


def test_get_pack_returns_metadata() -> None:
    for pid in ("python-pytest", "typescript-eslint", "php-phpunit"):
        pack = get_pack(pid)
        assert pack is not None
        assert pack["trust"] == "official"


def test_all_packs_iterable() -> None:
    packs = list(all_packs())
    assert len(packs) >= 3