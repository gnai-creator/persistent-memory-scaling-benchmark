from pathlib import Path

from persistent_memory_scaling.finalization import audit, inspect_artifact, markdown


def test_single_system_rows_require_exact_cardinality(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text('{"rows":[{"system":"asm"},{"system":"asm"}]}')
    spec = {"id": "asm", "path": "result.json", "kind": "single_system_rows", "system": "asm"}
    assert inspect_artifact(tmp_path, spec, 2).status == "ready"
    assert inspect_artifact(tmp_path, spec, 3).status == "running"


def test_multi_system_rows_check_every_executed_system(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        '{"protocol":{"executed_systems":["a","b"]},'
        '"rows":[{"system":"a"},{"system":"a"},{"system":"b"}]}'
    )
    spec = {
        "id": "hybrids",
        "path": "result.json",
        "kind": "multi_system_rows",
        "systems_from": "protocol.executed_systems",
    }
    check = inspect_artifact(tmp_path, spec, 2)
    assert check.status == "running"
    assert "b=1/2" in check.detail


def test_complete_result_requires_declaration_and_examples(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text('{"decision":{"complete":true},"summary":{"x":{"examples":128}}}')
    spec = {"id": "r32", "path": "result.json", "kind": "complete_result"}
    assert inspect_artifact(tmp_path, spec, 128).status == "ready"


def test_audit_and_markdown_do_not_promote_missing_artifact(tmp_path: Path) -> None:
    config = {
        "protocols": [{
            "id": "p",
            "label": "Protocol",
            "expected_questions": 1,
            "artifacts": [{"id": "missing", "path": "missing.json", "kind": "trustgraph_rows"}],
        }]
    }
    report = audit(tmp_path, config)
    assert report["benchmark_ready"] is False
    assert "NOT READY" in markdown(report)
