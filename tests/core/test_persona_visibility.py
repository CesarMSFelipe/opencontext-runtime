"""Tests for Persona.visibility, public_personas(), delegation_personas()."""

from __future__ import annotations

from argparse import Namespace

from opencontext_cli.commands.persona_cmd import handle_persona
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
        assert p.visibility == "hidden_delegation"


def test_public_visibility_value():
    for p in public_personas():
        assert str(p.visibility).startswith("public")


def test_no_overlap():
    pub_ids = {p.id for p in public_personas()}
    del_ids = {p.id for p in delegation_personas()}
    assert pub_ids.isdisjoint(del_ids)


def test_persona_list_default_shows_only_public(capsys):
    rc = handle_persona(Namespace(persona_command="list"))
    assert rc == 0
    out = capsys.readouterr().out
    for pid in _PUBLIC_IDS:
        assert pid in out
    for p in delegation_personas():
        assert p.id not in out


def test_persona_list_all_shows_all(capsys):
    rc = handle_persona(Namespace(persona_command="list", all=True, delegates=False))
    assert rc == 0
    out = capsys.readouterr().out
    for p in PERSONAS:
        assert p.id in out


def test_persona_list_delegates_shows_only_delegation(capsys):
    rc = handle_persona(Namespace(persona_command="list", all=False, delegates=True))
    assert rc == 0
    out = capsys.readouterr().out
    for pid in _PUBLIC_IDS:
        assert pid not in out
    assert len(delegation_personas()) == 10
    for p in delegation_personas():
        assert p.id in out
