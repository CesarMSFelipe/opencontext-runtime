"""Tests for Persona.visibility, public_personas(), delegation_personas()."""

from __future__ import annotations

from opencontext_core.personas import (
    PERSONAS,
    delegation_personas,
    public_personas,
)

_PUBLIC_IDS = {"oc-orchestrator", "oc-professor", "oc-reviewer"}


def test_public_personas_count():
    assert len(public_personas()) == 3


def test_public_personas_exact_ids():
    assert {p.id for p in public_personas()} == _PUBLIC_IDS


def test_delegation_personas_count():
    assert len(delegation_personas()) == 10


def test_completeness_guard():
    assert len(public_personas()) + len(delegation_personas()) == len(PERSONAS)


def test_default_visibility_is_delegation():
    for p in delegation_personas():
        assert p.visibility == "delegation"


def test_public_visibility_value():
    for p in public_personas():
        assert p.visibility == "public"


def test_no_overlap():
    pub_ids = {p.id for p in public_personas()}
    del_ids = {p.id for p in delegation_personas()}
    assert pub_ids.isdisjoint(del_ids)
