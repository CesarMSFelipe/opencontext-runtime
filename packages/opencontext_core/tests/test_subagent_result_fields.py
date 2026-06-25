from __future__ import annotations

from opencontext_core.agents.delegation import SubAgentResult


class TestSubAgentResultNewFields:
    def test_envelope_defaults_to_none(self):
        result = SubAgentResult(status="success", output="done")
        assert result.envelope is None

    def test_skill_path_defaults_to_none(self):
        result = SubAgentResult(status="success", output="done")
        assert result.skill_path is None

    def test_memory_policy_defaults_to_empty_dict(self):
        result = SubAgentResult(status="success", output="done")
        assert result.memory_policy == {}

    def test_token_usage_defaults_to_empty_dict(self):
        result = SubAgentResult(status="success", output="done")
        assert result.token_usage == {}

    def test_can_set_envelope(self):
        payload = {
            "run_id": "r",
            "change_id": "c",
            "phase": "apply",
            "status": "passed",
            "duration_s": 0.5,
        }
        result = SubAgentResult(status="success", output="done", envelope=payload)
        assert result.envelope == payload

    def test_can_set_skill_path(self):
        result = SubAgentResult(status="success", output="done", skill_path="skills/my-skill.md")
        assert result.skill_path == "skills/my-skill.md"

    def test_can_set_memory_policy(self):
        result = SubAgentResult(
            status="success", output="done", memory_policy={"layer": "EPISODIC"}
        )
        assert result.memory_policy == {"layer": "EPISODIC"}

    def test_can_set_token_usage(self):
        result = SubAgentResult(
            status="success", output="done", token_usage={"input": 100, "output": 50}
        )
        assert result.token_usage == {"input": 100, "output": 50}

    def test_existing_fields_unchanged(self):
        result = SubAgentResult(
            status="failed",
            output="",
            artifacts=["file.py"],
            error="Something broke",
            metadata={"run_id": "abc"},
        )
        assert result.status == "failed"
        assert result.artifacts == ["file.py"]
        assert result.error == "Something broke"
        assert result.metadata == {"run_id": "abc"}
