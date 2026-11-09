#!/usr/bin/env python3
"""Offline diagnostics on unchanged saved IR; no generation or semantic score."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v2_fusion_v2_3 as runner


def main():
    p = runner.prepare()
    source = runner.ROOT / p['design']['diagnosed_run']
    output = runner.ROOT / 'audit/outputs' / ('package_v2_fusion_feedback_v2_3__'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    print('Offline public diagnostics; no LLM or semantic evaluation.\nOutput: ' + str(output), flush=True)
    cells = sorted((source / 'cells').iterdir())
    original_workspace = next(c / 'workspace' for c in cells if '_m4_' in c.name)
    workspace = output / 'workspace'; workspace.mkdir()
    # Retain original catalog/bookkeeping to isolate diagnostics. Only the
    # contract identifier changes for tool loading; no IR fields are changed.
    for name in ('task.md', 'catalog', 'candidates', 'contracts', 'schemas', 'fixtures', 'workspace.yaml'):
        path = original_workspace / name
        if path.is_dir(): shutil.copytree(path, workspace / name)
        else: shutil.copy2(path, workspace / name)
    contract = json.loads((original_workspace / 'v2_contract.json').read_text())
    contract['version'] = runner.public.VERSION
    runner.controls.write_json(workspace / 'v2_contract.json', contract)
    rows = []
    for cell in cells:
        if not any('_' + m + '_' in cell.name for m in ('m3', 'm4')): continue
        for response_path in sorted((cell / 'llm').glob('*/response.json')):
            response = runner.replay.read_json(response_path)
            raw = response['response']['choices'][0]['message']['content']
            target = output / 'responses' / cell.name / response_path.parent.name
            submission = target / 'submission'; submission.mkdir(parents=True)
            ir = submission / 'serviceflow.yaml'; ir.write_text(raw)
            before = runner.controls.sha256(ir)
            try:
                runner.public.compile_submission(workspace, submission)
            except Exception as exc:
                runner.controls.write_json(target / 'compile_error.json', {'type': type(exc).__name__, 'message': str(exc)})
            report = runner.public.validate_submission(workspace, submission, run_execution=False)
            runner.controls.write_json(target / 'public_validation.json', report)
            unchanged = runner.controls.sha256(ir) == before
            if not unchanged: raise ValueError('Diagnostic replay changed saved IR')
            causes = [d for g in report['gates'] if g['gate'] == 'G3' for d in g['diagnostics'] if d['code'] == 'V2_INPUT_BINDING_CONTRACT']
            schema_failure = any(d['code'] == 'G0_SCHEMA_ERROR' for d in report['gates'][0]['diagnostics'])
            if report['overall_status'] != 'fail' or (not schema_failure and len(causes) != 3):
                raise ValueError('Unexpected diagnostic pattern; inspect before any generation')
            rows.append({'cell': cell.name, 'stage': response_path.parent.name,
                'source_response': str(response_path), 'source_response_sha256': runner.controls.sha256(response_path),
                'saved_ir_unchanged': unchanged, 'overall': report['overall_status'],
                'first_failing_gate': report['first_failing_gate'], 'schema_failure': schema_failure,
                'localized_input_failures': causes})
    if len(rows) != 5: raise ValueError('Expected M3 initial answer and all four M4 responses')
    runner.parent.verify_hashes(source, runner.replay.read_json(source / 'run.json'))
    runner.controls.write_json(output / 'result.json', {'status': 'complete', 'source': str(source),
        'freeze_id': p['freeze']['freeze_id'], 'model_calls': 0, 'semantic_evaluation': False,
        'original_scores_replaced': False, 'original_catalog_retained_for_diagnostic_isolation': True,
        'tool_contract_id_adapted_only': True, 'rows': rows})
    lines = ['# V2.3 offline feedback verification', '',
        'No LLM calls, business evaluation or replacement scores. Original source pins verified.',
        'The original catalog is retained to isolate diagnostics; the tool contract identifier is adapted.', '',
        '| Saved cell/stage | Unchanged IR | First failure | Schema error | Localized input errors |',
        '|---|---|---|---|---|']
    lines.extend(f"| {r['cell']}/{r['stage']} | {r['saved_ir_unchanged']} | {r['first_failing_gate']} | {r['schema_failure']} | {len(r['localized_input_failures'])} |" for r in rows)
    (output / 'summary.md').write_text('\n'.join(lines) + '\n')
    print('complete: ' + str(output / 'summary.md'), flush=True)
    return 0


if __name__ == '__main__': raise SystemExit(main())
