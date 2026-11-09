#!/usr/bin/env python3
"""Offline corpus census: original availability, public contracts, and context."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime,timezone
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import plan_v2_corpus_replay as legacy
import corpus_census_analysis as analysis

controls,replay,parent=legacy.controls,legacy.replay,legacy.parent
CONFIG=ROOT/'audit/v2/corpus_census.json'
TESTS=ROOT/'tests/unit/test_v2_corpus_census.py'
FILES=[Path(__file__).resolve(),CONFIG,TESTS,ROOT/'audit/v2/CORPUS_CENSUS.md',ROOT/'audit/v2/corpus_census_analysis.py']


def verify_roster(sources,cases,config):
    if len(cases)!=config['expected_pipelines'] or len(set(cases))!=len(cases): raise ValueError('Incorrect original pipeline roster')
    if any(not re.fullmatch(r'(main|validation|extension)/[a-z0-9_]+',case) for case in cases): raise ValueError('Unsafe case identity')
    if Counter(c.split('/')[0] for c in cases)!=config['expected_strata']: raise ValueError('Original strata differ')
    expected=set(itertools.product(config['models'],config['methods'],cases,config['samples']))
    actual=[]
    for source in sources:
        identity=(source['model'],source['method'],source['case'],source['sample_index'])
        if source['id']!='/'.join(map(str,identity)): raise ValueError('Cell identity disagrees with source')
        if source['route']!=('direct_argo' if source['method'] in ('m0','m1','m2') else 'serviceflow_ir'): raise ValueError('Changed cell route')
        actual.append(identity)
    if len(sources)!=config['expected_cells'] or len(set(actual))!=len(actual) or set(actual)!=expected:
        raise ValueError('Missing, duplicated, or changed original cell roster')


def prepare():
    config=replay.read_json(CONFIG)
    coverage_root=ROOT/config['parent_coverage']; coverage=replay.read_json(coverage_root/'run.json')
    if coverage['status'] not in ('complete','complete_with_errors') or coverage.get('source_inputs_unchanged') is not True:
        raise ValueError('Original coverage evidence is incomplete or changed')
    hashes=parent.verify_hashes(coverage_root,coverage)
    cells=replay.read_json(coverage_root/'saved_cell_coverage.json'); sources=[c['source'] for c in cells]
    errors={c['source']['id'] for c in cells if c['analysis']['state'] in ('inspection_error','planner_error')}
    if errors!=set(config['known_parent_inspection_errors']): raise ValueError('Unexpected prior inspection errors')
    references=replay.read_json(coverage_root/'pipeline_coverage.json'); cases=sorted(r['case'] for r in references)
    verify_roster(sources,cases,config)
    if {s['id']:s for s in coverage['sources']}!={s['id']:s for s in sources}: raise ValueError('Coverage ledger/source identities changed')
    paired_root=ROOT/config['parent_paired']; paired=replay.read_json(paired_root/'run.json')
    if paired['status']!='complete' or paired.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged paired evidence required')
    paired_hashes=parent.verify_hashes(paired_root,paired)
    for name,digest in paired_hashes.items():
        if name in hashes and hashes[name]!=digest: raise ValueError('Prior audit input pins disagree')
        hashes[name]=digest
    inventory=replay.read_json(ROOT/replay.read_json(parent.CONFIG)['inventory_run']/'run.json')
    baseline=Path(inventory['control_directory'])
    # Pin all current public workspace files as well as old parent inputs. Each
    # case separately verifies these files against its builder inventory.
    for case in cases:
        workspace=baseline/'cases'/case/'public_workspace'/case
        for path in workspace.rglob('*'):
            if path.is_file():
                resolved=path.resolve()
                if not resolved.is_relative_to(workspace.resolve()): raise ValueError('Public workspace file escapes its root')
                digest=controls.sha256(path); name=str(resolved)
                if name in hashes and hashes[name]!=digest: raise ValueError('Pinned public file changed')
                hashes[name]=digest
    paths=[*FILES,coverage_root/'run.json',coverage_root/'input_sha256.json',coverage_root/'saved_cell_coverage.json',
           coverage_root/'pipeline_coverage.json',paired_root/'run.json',paired_root/'input_sha256.json',ROOT/'schemas/serviceflow_ir.schema.json']
    hashes.update({str(p.resolve()):controls.sha256(p) for p in paths})
    schema=replay.read_json(ROOT/'schemas/serviceflow_ir.schema.json')
    analysis.Draft202012Validator.check_schema(schema)
    if any(isinstance(v,dict) and any(k in v and not str(v[k]).startswith('#') for k in ('$ref','$dynamicRef')) for v in legacy.analysis.walk(schema)):
        raise ValueError('IR schema has nonlocal references; no fetching is permitted')
    return config,sources,cases,baseline,schema,hashes


class Catalog:
    def __init__(self): self.base=legacy.analysis.Catalog(controls.load); self.cache={}
    def get(self,workspace,service,version):
        key=(str(workspace.resolve()),service,version)
        if key not in self.cache: self.cache[key]=self.base.get(workspace,service,version)
        return self.cache[key]


def public_context(workspace):
    manifest=controls.load(workspace/'workspace.yaml')
    for entry in manifest['files']:
        path=analysis.safe_path(workspace,entry['path'])
        if not path.is_file() or controls.sha256(path)!=entry['sha256']: raise ValueError('Public workspace builder checksum mismatch')
    scenarios=replay._fixture_scenarios(workspace)
    return {'builder':manifest.get('builder'), 'exclusions':manifest.get('exclusions',[]),
            'verified_file_count':len(manifest['files']),'scenarios':scenarios}


def inspect_ir(path,workspace,scenarios,schema,catalog,config):
    if not path.is_file(): return analysis.result('missing_saved_ir',[],[],[],[])
    if path.stat().st_size>config['max_document_bytes']: return analysis.result('inspection_limit',[],[],[],[])
    try: ir=controls.load(path)
    except (ValueError,TypeError,controls.yaml.YAMLError) as exc:
        result=analysis.result('parse_error',[],[],[],[]);result['error_type']=type(exc).__name__;return result
    return analysis.analyze(ir,schema=schema,catalog_get=lambda service,version:catalog.get(workspace,service,version),
        workspace=workspace,scenarios=scenarios,load=controls.load,maximum=config['max_document_bytes'],node_limit=config['max_document_nodes'])


def inspect_source(source,workspace,context,schema,catalog,config):
    path=Path(source['artifact'])
    record={'source':source,'artifact_sha256':controls.sha256(path) if path.is_file() else 'MISSING'}
    try:
        if source['route']=='direct_argo':
            result=legacy.inspect_argo(path,config['max_document_bytes'])
            result['findings']=[];result['finding_counts']={};result['semantic_outcome']='not_measured'
            result['scope']='Availability/YAML/resource inventory only; no IR-contract comparison'
        else: result=inspect_ir(path,workspace,context['scenarios'],schema,catalog,config)
    except Exception as exc:
        result=analysis.result('inspection_error',[{'category':'inspection_error','code':'cell_inspection_error','subject':'document','error_type':type(exc).__name__}],[],[],[])
    record['analysis']=result;return record


def case_record(case,sources,baseline,schema,catalog,config):
    workspace=baseline/'cases'/case/'public_workspace'/case
    try: context=public_context(workspace)
    except Exception as exc:
        error=analysis.result('inspection_error',[{'category':'inspection_error','code':'public_workspace_context_error','subject':case,'error_type':type(exc).__name__}],[],[],[])
        return {'reference':{'case':case,'analysis':error},'public_context':{'state':'inspection_error'},
                'model_cells':[{'source':s,'analysis':error} for s in sources]}
    reference=controls.BENCHMARK/'instances'/case/'gold/serviceflow.yaml'
    try: reference_analysis=inspect_ir(reference,workspace,context['scenarios'],schema,catalog,config)
    except Exception as exc: reference_analysis=analysis.result('inspection_error',[{'category':'inspection_error','code':'reference_inspection_error','subject':case,'error_type':type(exc).__name__}],[],[],[])
    return {'reference':{'case':case,'reference_ir_sha256':controls.sha256(reference) if reference.is_file() else 'MISSING',
                         'role':'structural public-contract/implementation planning only; never replacement model bindings','analysis':reference_analysis},
            'public_context':context,'model_cells':[inspect_source(s,workspace,context,schema,catalog,config) for s in sources]}


def group_counts(cells):
    groups={}
    for row in cells:
        source,a=row['source'],row['analysis'];key=(source['model'],source['method'],source['route'])
        group=groups.setdefault(key,{'model':key[0],'method':key[1],'route':key[2],'declared':0,'artifact_present':0,'cells_with_structure_or_dataflow':0,
            'states':Counter(),'original_method_statuses':Counter(),'cells_by_category':Counter(),'findings_by_category':Counter()})
        group['declared']+=1;group['artifact_present']+=row.get('artifact_sha256','MISSING')!='MISSING'
        group['states'][a['state']]+=1;group['original_method_statuses'][str(source.get('original_method_status'))]+=1
        findings=a.get('findings',[])
        group['cells_with_structure_or_dataflow']+=any(f['category'] in ('saved_structure','dataflow') for f in findings)
        group['cells_by_category'].update({f['category'] for f in findings})
        group['findings_by_category'].update(f['category'] for f in findings)
    return [{**g,**{k:dict(g[k]) for k in ('states','original_method_statuses','cells_by_category','findings_by_category')}} for _,g in sorted(groups.items())]


def service_inventory(records):
    inventory={}
    for record in records:
        pairs=[('reference',record['reference']['case'],record['reference']['analysis'])]
        pairs.extend(('model',c['source']['id'],c['analysis']) for c in record['model_cells'] if c['source']['route']=='serviceflow_ir')
        for role,identity,a in pairs:
            for s in a.get('services',[]):
                if not isinstance(s.get('service_id'),str) or not isinstance(s.get('service_version'),str):continue
                key=s['service_id']+'@'+s['service_version']
                row=inventory.setdefault(key,{'service':key,'reference_cases':set(),'model_cells':set(),'descriptor_variants':{}})
                row['reference_cases' if role=='reference' else 'model_cells'].add(identity)
                if s.get('descriptor_fingerprint'):
                    row['descriptor_variants'][s['descriptor_fingerprint']]=s['signals']
    return [{**r,'reference_cases':sorted(r['reference_cases']),'model_cells':sorted(r['model_cells']),
             'reference_pipeline_count':len(r['reference_cases']),'model_cell_count':len(r['model_cells'])} for _,r in sorted(inventory.items())]


def aggregate(records):
    cells=[c for r in records for c in r['model_cells']]; references=[r['reference'] for r in records]
    ir=[c for c in cells if c['source']['route']=='serviceflow_ir'];direct=[c for c in cells if c['source']['route']=='direct_argo']
    codes=Counter((f['category'],f['code']) for c in ir for f in c['analysis'].get('findings',[]))
    categories={cat:sum(any(f['category']==cat for f in c['analysis'].get('findings',[])) for c in ir) for cat in analysis.CATEGORIES}
    return {'original_pipeline_count':len(references),'model_cell_count':len(cells),'ir_cell_count':len(ir),'direct_argo_cell_count':len(direct),
        'ir_states':dict(Counter(c['analysis']['state'] for c in ir)),'direct_states':dict(Counter(c['analysis']['state'] for c in direct)),
        'ir_cells_by_category':categories,
        'ir_cells_with_checked_hard_findings':sum(any(f['category'] in analysis.HARD for f in c['analysis'].get('findings',[])) for c in ir),
        'ir_cells_inspected_without_checked_hard_findings':sum(c['analysis']['state']=='inspected' and not any(f['category'] in analysis.HARD for f in c['analysis'].get('findings',[])) for c in ir),
        'finding_codes':[{'category':cat,'code':code,'findings':n} for (cat,code),n in sorted(codes.items())],
        'by_model_method':group_counts(cells),'service_inventory':service_inventory(records),'reference_families':analysis.family_groups(references),
        'scope':'Static overlapping diagnostics, not semantic scores or certified execution readiness'}


def render(run,summary):
    lines=['# Corpus-wide static root-cause census','',f"Protocol {run['audit_protocol_version']}; state {run['status']}; pipelines {summary['original_pipeline_count']}; original cells {summary['model_cell_count']}.",
        'Zero LLM calls, workflow executions, repairs, or semantic scores. Original publication/results unchanged.','',
        'M3–M5 are inspected as IR. M0–M2 retain a separate availability/YAML/resource inventory route.','',
        '## IR availability and inspection','', '| State | Cells |','|---|---:|']
    lines.extend(f'| {k} | {v} |' for k,v in sorted(summary['ir_states'].items()))
    lines+=['','## IR findings (overlapping cell counts)','', '| Category | Cells affected |','|---|---:|']
    lines.extend(f'| {k} | {v} |' for k,v in summary['ir_cells_by_category'].items())
    lines+=['','`frozen_type_rule` records the old validator\'s literal type equality, including `any`; it is not a new semantic-failure judgment.',
        'Input/runtime context and descriptive semantic signals are review needs, not automatically model errors.','',
        '## Pooled model/method counts','', '| Model | Method | Route | Declared | Present | Inspected/inventoried | Contract | Structure/dataflow | Input context |','|---|---|---|---:|---:|---:|---:|---:|---:|']
    for group in summary['by_model_method']:
        c=group['cells_by_category'];inspected=group['states'].get('inspected',0)+group['states'].get('direct_artifact_inventoried',0)
        combined=group['cells_with_structure_or_dataflow']
        lines.append(f"| {group['model']} | {group['method']} | {group['route']} | {group['declared']} | {group['artifact_present']} | {inspected} | {c.get('catalog_contract',0) if group['route']=='serviceflow_ir' else '-'} | {combined if group['route']=='serviceflow_ir' else '-'} | {c.get('input_context',0) if group['route']=='serviceflow_ir' else '-'} |")
    lines+=['','## Reference-only service-roster groups for review','',
        'Ranking is a workload/public-information proposal, not execution authorization or selection by model success.','',
        '| Rank | Roster ID | Reference pipelines | Services | Reference review | External review | Input review |','|---:|---|---:|---:|---:|---:|---:|']
    for row in summary['reference_families'][:12]:
        lines.append(f"| {row['rank']} | {row['family_id']} | {row['reference_pipeline_count']} | {row['unique_service_count']} | {row['reference_review_count']} | {row['external_execution_review_count']} | {row['reference_input_review_count']} |")
    lines+=['','Same service roster does not prove the same numerical semantics; descriptor variants are retained in service_inventory.json.',
        'See full per-case diagnostics, model_method.csv, findings.csv, reference_families.json, and input/code fingerprints.',
        'All original stratum labels are retained in per-cell outputs; headline summaries pool all 110 pipelines.','']
    return '\n'.join(lines)


def csv_outputs(output,summary,cells):
    stream=io.StringIO(newline='');fields=['model','method','route','declared','artifact_present',*analysis.CATEGORIES]
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for row in summary['by_model_method']:
        writer.writerow({**{k:row[k] for k in fields[:5]},**{cat:row['cells_by_category'].get(cat,0) if row['route']=='serviceflow_ir' else '' for cat in analysis.CATEGORIES}})
    (output/'model_method.csv').write_text(stream.getvalue())
    stream=io.StringIO(newline='');fields=['cell','model','method','route','case','stratum','sample','original_method_status','state','artifact_present',*analysis.CATEGORIES]
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for row in cells:
        s,a=row['source'],row['analysis'];categories={f['category'] for f in a.get('findings',[])}
        writer.writerow({'cell':s['id'],**{k:s[k] for k in ('model','method','route','case')},'stratum':s['case'].split('/')[0],
            'sample':s['sample_index'],'original_method_status':s.get('original_method_status'),'state':a['state'],
            'artifact_present':row.get('artifact_sha256','MISSING')!='MISSING',
            **{cat:(cat in categories) if s['route']=='serviceflow_ir' else '' for cat in analysis.CATEGORIES}})
    (output/'cells.csv').write_text(stream.getvalue())
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=['cell','model','method','case','stratum','sample','original_method_status','state','category','code','subject']);writer.writeheader()
    for cell in cells:
        s,a=cell['source'],cell['analysis']
        for f in a.get('findings',[]):writer.writerow({'cell':s['id'],'model':s['model'],'method':s['method'],'case':s['case'],'stratum':s['case'].split('/')[0],
            'sample':s['sample_index'],'original_method_status':s.get('original_method_status'),'state':a['state'],**{k:f[k] for k in ('category','code','subject')}})
    (output/'findings.csv').write_text(stream.getvalue())


def read_checkpoints(run,cases):
    records=[]
    for case in cases:
        saved=run['completed_cases'][case];path=Path(saved['path'])
        if controls.sha256(path)!=saved['sha256']:raise ValueError('Completed census checkpoint changed')
        record=replay.read_json(path)
        expected={s['id'] for s in run['sources'] if s['case']==case}
        actual=[c['source']['id'] for c in record['model_cells']]
        if record['reference']['case']!=case or len(actual)!=len(set(actual)) or set(actual)!=expected:
            raise ValueError('Checkpoint source roster changed')
        records.append(record)
    return records


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv)
    print('Verifying immutable prior evidence, the full original roster, and public workspaces...',flush=True)
    config,sources,cases,baseline,schema,hashes=prepare()
    if args.dry_run:
        print(json.dumps({'original_pipelines':len(cases),'original_cells':len(sources),'routes':dict(Counter(s['route'] for s in sources)),
            'reference_ir_controls':len(cases),'llm_calls':0,'workflow_executions':0,'repairs':0,'semantic_scores':0},indent=2));return 0
    if args.resume:
        output=args.resume.resolve();run=replay.read_json(output/'run.json')
        if run['input_fingerprint']!=controls.fingerprint(hashes) or run['sources']!=sources or run['cases']!=cases:
            raise ValueError('Census code/design/inputs changed; cannot resume')
        if set(run['completed_cases'])-set(cases):raise ValueError('Unknown completed case checkpoint')
        read_checkpoints(run,sorted(run['completed_cases']))
    else:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');output=ROOT/'audit/outputs'/f'package_v2_corpus_census__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True,exist_ok=False)
        run={'package_version':config['package_version'],'audit_protocol_version':config['audit_protocol_version'],'design':config,'sources':sources,'cases':cases,
            'input_fingerprint':controls.fingerprint(hashes),'environment':controls.environment(),'completed_cases':{},'llm_calls':0,'workflow_executions':0,'repairs':0,'semantic_scores':0}
        controls.write_json(output/'input_sha256.json',hashes)
        for path in FILES:
            target=output/'implementation'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    run['status']='running';controls.write_json(output/'run.json',run);print(f'Output: {output}',flush=True)
    test=subprocess.run([sys.executable,'-m','pytest','-q',str(TESTS)],cwd=ROOT,capture_output=True,text=True,timeout=60)
    (output/'verification.txt').write_text(test.stdout+test.stderr)
    if test.returncode:
        run['status']='verification_failed';controls.write_json(output/'run.json',run);print(f'verification_failed: {output / "verification.txt"}',flush=True);return 1
    grouped=defaultdict(list)
    for source in sources:grouped[source['case']].append(source)
    catalog=Catalog()
    for number,case in enumerate(cases,1):
        if case in run['completed_cases']:continue
        record=case_record(case,grouped[case],baseline,schema,catalog,config)
        target=output/'cases'/case/('attempt_'+uuid.uuid4().hex[:8])/'census.json'
        controls.write_json(target,record);run['completed_cases'][case]={'path':str(target),'sha256':controls.sha256(target)}
        controls.write_json(output/'run.json',run);print(f'[{number}/{len(cases)}] {case}: {len(record["model_cells"])} model cells recorded',flush=True)
    records=read_checkpoints(run,cases)
    summary=aggregate(records);cells=[c for record in records for c in record['model_cells']]
    for name,value in [('aggregate_census',summary),('saved_cell_census',cells),('reference_census',[r['reference'] for r in records]),
                       ('service_inventory',summary['service_inventory']),('reference_families',summary['reference_families'])]:controls.write_json(output/(name+'.json'),value)
    csv_outputs(output,summary,cells)
    try:parent.verify_hashes(output,run);unchanged=True
    except ValueError as exc:unchanged=False;run['integrity_error']=str(exc)
    errors=any(r['reference']['analysis']['state'] in ('inspection_error','inspection_limit') or r['reference']['analysis'].get('finding_counts',{}).get('inspection_error',0)
        or any(c['analysis']['state'] in ('inspection_error','inspection_limit') or c['analysis'].get('finding_counts',{}).get('inspection_error',0) for c in r['model_cells']) for r in records)
    complete=len(cells)==config['expected_cells'] and len(records)==config['expected_pipelines']
    run['source_inputs_unchanged']=unchanged;run['status']='inputs_changed' if not unchanged else 'complete_with_errors' if errors or not complete else 'complete'
    controls.write_json(output/'run.json',run)
    (output/'summary.md').write_text(render(run,summary))
    print(run['status']+': '+str(output/'summary.md'),flush=True)
    return 0 if run['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
