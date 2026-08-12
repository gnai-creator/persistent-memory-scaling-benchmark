from persistent_memory_scaling.longmemeval_fixed_context_plot import BUDGETS, SYSTEMS, measurements


def test_measurements_extract_official_endpoint_results_and_failures() -> None:
    rows = []
    summary = {}
    official = {}
    for system in SYSTEMS:
        for budget in BUDGETS:
            key = f"{system}_b{budget}"
            summary[key] = {
                "reader_input_tokens_mean": budget + 100,
                "reader_input_tokens_total": (budget + 100) * 2,
                "reader_latency_ms_mean": 1234,
                "retrieval_recall": .5,
            }
            official[key] = {"examples": 2, "correct": 1, "accuracy": .5}
            rows.extend([
                {"system": system, "evidence_token_budget": budget, "reader_contract_failure": False},
                {"system": system, "evidence_token_budget": budget, "reader_contract_failure": budget == 2000},
            ])
    data = measurements({
        "complete": True,
        "rows": rows,
        "summary": summary,
        "official_evaluation": {"results": official},
    })
    assert data[("asm_bridge81", 2000)]["accuracy"] == 50
    assert data[("asm_bridge81", 2000)]["contract_failures"] == 1
    assert data[("asm_bridge81", 28000)]["contract_failures"] == 0
