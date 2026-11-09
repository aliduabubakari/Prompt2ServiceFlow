"""Standalone stdlib-only file-backed mock evidence kernel; embedded verbatim.

This observes public files and declared predecessor artifacts. It does not
execute the service's domain operation or read any assertion/reference answer.
"""
import csv
import hashlib
import json
from pathlib import Path


def bounded_file(root,relative):
    root=Path(root).resolve();path=(root/relative).resolve()
    if not path.is_relative_to(root):raise ValueError('Evidence path escapes its root')
    if path.is_symlink():raise ValueError('Symlink evidence is not permitted')
    return path


def describe_public_file(path,root):
    data=path.read_bytes();suffix=path.suffix.lower()
    if suffix=='.csv':
        with path.open(encoding='utf-8',newline='') as handle:count=sum(1 for _ in csv.DictReader(handle))
    elif suffix in ('.json','.geojson'):
        value=json.loads(data);count=len(value) if isinstance(value,list) else 1
    elif suffix in ('.jsonl','.ndjson'):
        count=0
        for line in data.decode('utf-8').splitlines():
            if line.strip():json.loads(line);count+=1
    elif suffix in ('.txt','.sql','.conf','.yaml','.yml','.md'):
        count=sum(bool(line.strip()) for line in data.decode('utf-8').splitlines())
    elif suffix=='.pdf':
        if not data.startswith(b'%PDF-'):raise ValueError('Invalid PDF signature')
        count=1 if data else 0
    elif suffix=='.png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG signature')
        count=1 if data else 0
    else:count=1 if data else 0
    return {'name':path.relative_to(root).as_posix(),'size_bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest(),'record_count':count}


def fixture_observation(root):
    root=Path(root);files=[];errors=[];configuration=[]
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(root).as_posix()
        try:
            bounded_file(root,relative)
            # This published benchmark wrapper declares inputs; it is not a
            # data record and its contents are not copied into output evidence.
            if relative=='fixture.json':
                value=json.loads(path.read_text(encoding='utf-8'))
                if isinstance(value,dict) and isinstance(value.get('inputs'),dict) and 'input_modalities' in value:
                    configuration.append({'name':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()});continue
            files.append(describe_public_file(path,root))
        except (ValueError,UnicodeError,OSError) as exc:errors.append({'path':relative,'error':type(exc).__name__+': '+str(exc)[:300]})
    if not files:errors.append({'error':'No public data files available'})
    if sum(f['record_count'] for f in files)==0:errors.append({'error':'No public data records available'})
    return {'file_count':len(files),'record_count':sum(f['record_count'] for f in files),
        'files':files,'configuration_files':configuration},errors


def output_relative(spec):
    name=spec['artifact_id']
    if spec.get('execution_evidence') or 'json_value' in spec:return 'artifacts/'+name+'.json'
    if spec['data_type'] in ('csv','table'):return 'artifacts/'+name+'.csv'
    if spec['data_type'] in ('binary','image') or spec.get('media_type')=='application/pdf':return 'artifacts/'+name+('.pdf' if spec.get('media_type')=='application/pdf' else '.bin')
    return 'artifacts/'+name+('.md' if spec['data_type']=='markdown' else '.txt')


def execution_observation(args,task):
    if task['profile_enabled']:fixture,errors=fixture_observation(args.fixtures)
    else:fixture,errors={'file_count':0,'record_count':0,'files':[],'configuration_files':[]},[]
    upstream=[]
    errors.extend({'error':message} for message in task.get('binding_errors',[]))
    for wanted in task['upstream']:
        try:
            path=bounded_file(args.workspace,wanted['path'])
            receipt=bounded_file(args.workspace,'execution_receipts/'+wanted['intent_id']+'.json')
            document=json.loads(receipt.read_text(encoding='utf-8'))
            if document['intent_id']!=wanted['intent_id']:raise ValueError('Producer receipt identity mismatch')
            observed=[o for o in document['outputs'] if o['artifact_id']==wanted['artifact_id'] and o['path']==wanted['path']]
            if len(observed)!=1 or not path.is_file():raise ValueError('Declared upstream artifact was not produced')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if observed[0]['sha256']!=digest:raise ValueError('Upstream artifact changed after its producer ran')
            if not document['success']:raise ValueError('Declared upstream task reported failure')
            upstream.append({**wanted,'sha256':digest,'size_bytes':path.stat().st_size})
        except (ValueError,KeyError,OSError) as exc:errors.append({'upstream':wanted,'error':type(exc).__name__+': '+str(exc)[:300]})
    return {'profile_version':'fixture-execution-evidence/1','success':not errors,'errors':errors,
        'task':task['intent_id'],'fixture':fixture,'upstream_artifact_count':len(upstream),'upstream_artifacts':upstream}


def evidence_payload(spec,observation):
    # Retain existing domain/example fields. New telemetry cannot rewrite a
    # public contract's constants or numerical output values.
    payload=dict(spec.get('json_value') or {})
    for key in ['success','errors','task','fixture','upstream_artifact_count','upstream_artifacts']:
        if key not in payload:payload[key]=observation[key]
    payload.setdefault('artifact',spec['artifact_id'])
    payload['execution_evidence']=observation
    return payload


def write_execution_receipt(args,task,specs,observation):
    outputs={}
    for spec in specs:
        relative=output_relative(spec);path=bounded_file(args.workspace,relative)
        if path.is_file():
            archived='execution_artifacts/'+task['intent_id']+'/'+Path(relative).name
            archive=bounded_file(args.workspace,archived);archive.parent.mkdir(parents=True,exist_ok=True);archive.write_bytes(path.read_bytes())
            outputs[(spec['artifact_id'],relative)]={'artifact_id':spec['artifact_id'],'path':archived,'visible_path':relative,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    receipt=bounded_file(args.workspace,'execution_receipts/'+task['intent_id']+'.json');receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps({'intent_id':task['intent_id'],'profile_version':'fixture-execution-evidence/1',
        'success':observation['success'] if observation is not None else True,'outputs':list(outputs.values())},sort_keys=True)+'\n')
