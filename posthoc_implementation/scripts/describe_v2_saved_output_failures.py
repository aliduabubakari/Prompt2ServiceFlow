#!/usr/bin/env python3
"""Explain already scored output failures without changing any score or file."""
import argparse
from collections import Counter,defaultdict
import csv
import json
from pathlib import Path

import analyze_v2_corpus_assertion_results as analysis


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.analysis.resolve();output=args.output.resolve()
    if output.exists() or output.is_relative_to(root):raise ValueError('Use a new separate output directory')
    hashes=json.loads((root/'SHA256.json').read_text())
    for relative,sha in hashes.items():
        path=analysis.replay.engine.metadata.bounded.safe(root,relative)
        if analysis.replay.controls.sha256(path)!=sha:raise ValueError('Analysis evidence changed')
    provenance=json.loads((root/'provenance.json').read_text());source=Path(provenance['source_run'])
    seal=json.loads((source/'output_sha256.json').read_text())
    if seal['output_fingerprint']!=provenance['source_output_fingerprint']:raise ValueError('Replay source differs')
    analysis.replay.previous.previous.previous.verify_seal(source,seal)
    ledger=json.loads((source/'run.json').read_text())
    with (root/'positive_outputs.csv').open() as handle:outputs=list(csv.DictReader(handle))
    with (root/'assertion_level.csv').open() as handle:checks=list(csv.DictReader(handle))
    groups=defaultdict(list)
    for row in outputs:groups[row['cell_id']].append(row)
    payloads=Counter();files=set()
    for row in checks:
        if row['condition']!='output_role' or row['category']!='output_not_valid_json':continue
        directory=Path(ledger['completed_cells'][row['cell_id']]['path']).parent
        snapshot=directory/'scenarios'/row['scenario']/'snapshot'
        path=analysis.replay.engine.metadata.bounded.safe(snapshot,row['selected_path'])
        data=path.read_bytes();files.add(str(path))
        kind='generic_example_text' if data in (b'example\n',b'example\\n') else 'csv_header_only' if data in (b'value\r\n',b'value\n') else 'other_non_json'
        payloads[kind]+=1
    results={'positive_output_requirements':len(outputs),'positive_outputs_present':sum(r['state']=='present_nonempty' for r in outputs),
        'replayed_cells_with_positive_output_requirements':len(groups),
        'cells_with_all_required_positive_outputs_present':sum(all(r['state']=='present_nonempty' for r in rows) for rows in groups.values()),
        'format_error_check_payloads':dict(payloads),'unique_format_error_files':len(files),
        'scope':'Post-hoc output availability diagnostics conditional on the 797 replayed original-public-valid cells. Presence does not mean assertion success. No predicate or source output is changed.',
        'source_analysis':str(root),'source_output_fingerprint':seal['output_fingerprint'],
        'analysis_checksums_sha256':analysis.replay.controls.sha256(root/'SHA256.json'),
        'script_sha256':analysis.replay.controls.sha256(Path(__file__)), 'llm_calls':0,'runtime_executions':0}
    output.mkdir(parents=True);analysis.replay.engine.write(output/'diagnostics.json',results)
    analysis.replay.engine.write(output/'SHA256.json',analysis.replay.engine.files(output))
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
