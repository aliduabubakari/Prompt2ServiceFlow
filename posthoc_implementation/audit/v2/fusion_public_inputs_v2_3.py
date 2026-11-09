"""Deterministic public catalog overlay and bounded public reading bundles."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml

CONTEXT = 'public_context.json'
INTERFACES = 'public_interfaces.json'
MAX_BUNDLE_BYTES = 48 * 1024  # Below Pi's 50 KiB read-result cap.


def sha(data): return hashlib.sha256(data).hexdigest()


def catalog_overlay(workspace, constraints):
    workspace = Path(workspace)
    index = yaml.safe_load((workspace / 'catalog/catalog.yaml').read_text())
    index['version'] += '-semantic-v2.3'
    files = {}
    for row in index['services']:
        if row['service_id'] not in constraints: continue
        rule = constraints[row['service_id']]
        relative = 'catalog/' + row['descriptor_path']
        descriptor = yaml.safe_load((workspace / relative).read_text())
        port = next(p for p in descriptor['interface']['inputs'] if p['name'] == rule['port'])
        port['required'] = True
        port['cardinality'] = 'one' if rule['minimum'] == 1 else 'many'
        port['description'] = (f"Reference execution profile: exactly {rule['minimum']} distinct JSON artifact(s). "
            + ('Bind the supplied public manifest JSON as an input artifact.' if rule['source'] == 'public_manifest'
               else 'Bind upstream computation bundles; execution reports are separate.'))
        data = yaml.safe_dump(descriptor, sort_keys=False).encode()
        files[relative] = data; row['sha256'] = sha(data)
    if len(files) != len(constraints): raise ValueError('Public catalog is missing a registered service')
    files['catalog/catalog.yaml'] = yaml.safe_dump(index, sort_keys=False).encode()
    return files, index


def write_bundles(workspace, contract):
    """Read only named public sources; never walk results or private variants."""
    workspace = Path(workspace)
    candidates = yaml.safe_load((workspace / 'candidates/candidate_sets.yaml').read_text())
    ids = sorted({s for row in candidates['candidate_sets'] for s in row['service_ids']})
    core = {'bundle_version': 'public-inputs/2.3', 'task': (workspace / 'task.md').read_text(),
            'candidates': candidates, 'execution_contract': copy.deepcopy(contract),
            'note': 'Full original public files remain available. This bundle contains no reference composition or evaluation variants.'}
    interfaces = {'bundle_version': 'public-inputs/2.3',
        'serviceflow_schema': json.loads((workspace / 'schemas/serviceflow_ir.schema.json').read_text()),
        'candidate_descriptors': [yaml.safe_load((workspace / 'catalog/services' / (s + '.yaml')).read_text()) for s in ids],
        'artifact_contracts': {p.relative_to(workspace).as_posix(): json.loads(p.read_text()) for p in sorted((workspace / 'contracts').glob('*.json'))}}
    sizes = {}
    for name, document in ((CONTEXT, core), (INTERFACES, interfaces)):
        # One ordinary JSON value per top-level field keeps line count low;
        # no summary or truncation changes the underlying public facts.
        data = ('{\n' + ',\n'.join(json.dumps(k) + ':' + json.dumps(v, separators=(',', ':'), ensure_ascii=False)
                                     for k, v in document.items()) + '\n}\n').encode()
        if len(data) > MAX_BUNDLE_BYTES: raise ValueError(f'{name} exceeds the reviewed read cap; split bundles before inference')
        (workspace / name).write_bytes(data)
        sizes[name] = {'bytes': len(data), 'sha256': sha(data)}
    return sizes
