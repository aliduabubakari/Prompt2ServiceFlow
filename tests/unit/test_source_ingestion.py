from prompt2serviceflow.source_ingestion import concrete_edge_count, description_metrics


def test_description_metrics_marks_generic_validation_text_low() -> None:
    text = """Pipeline Steps:
1. extract - extract
  - Objective: implement this operation as a task in the workflow
  - Mechanism: python_callable
2. load - load
  - Objective: implement this operation as a task in the workflow
  - Mechanism: python_callable

Control Flow:
  - extract -> load
"""
    metrics = description_metrics(text)

    assert metrics["description_step_count"] == 2
    assert metrics["description_edge_count"] == 1
    assert metrics["generic_objective_count"] == 2
    assert metrics["information_sufficiency"] == "low"


def test_description_metrics_marks_detailed_text_high() -> None:
    text = """Control Flow:
  - extract -> load

Pipeline Steps:
1. extract - extract
  - Objective: Read a CSV file
  - Mechanism: python_callable
  - Inputs: file:/data/input.csv
  - Outputs: data:records
2. load - load
  - Objective: Load records into PostgreSQL
  - Mechanism: python_callable
  - Inputs: data:records
  - Outputs: table:records
"""
    metrics = description_metrics(text)

    assert metrics["description_step_count"] == 2
    assert metrics["description_edge_count"] == 1
    assert metrics["information_sufficiency"] == "high"


def test_concrete_edge_count_ignores_legacy_terminal_edge() -> None:
    spec = {
        "control_flow": {
            "edges": [
                {"from": "extract", "to": "load"},
                {"from": "load", "to": None},
            ]
        }
    }

    assert concrete_edge_count(spec) == 1
