"""Explicit append/replace PostgreSQL loaders and bounded local CSV control."""
from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path
import re

import service_executor as validation_base
import workflow_executor as file_base

SNAPSHOT = 'database_csv_snapshot_importer'
TABULAR = 'tabular_dataset_database_loader'
VERSION = 'p2sf.csv-postgresql/1'


class ContractError(ValueError):
    def __init__(self, code, message): super().__init__(message); self.code = code


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', value):
        raise ContractError('unsupported_identifier', 'Require a single explicit SQL identifier, at most 63 ASCII characters')
    return '"' + value + '"'


def literal(value):
    if not isinstance(value, str) or '\0' in value:
        raise ContractError('unsupported_text_value', 'Only non-NUL strings are supported by the TEXT load contract')
    return "'" + value.replace("'", "''") + "'"


def inside(root, relative):
    root = Path(root).resolve(); p = Path(relative); resolved = (root / p).resolve()
    if p.is_absolute() or '..' in p.parts or not resolved.is_relative_to(root):
        raise ContractError('unsafe_artifact_path', 'Artifact reference escapes its declared workspace')
    return resolved


def canonical_bytes(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode()


def validated(raw, required, *, fail_on_empty=True):
    try:
        text = raw.decode('utf-8')
        result = validation_base.compute('csv_tabular_schema_validating_loader',
            {'required_columns': required, 'has_header': True, 'delimiter': ',',
             'fail_on_empty': fail_on_empty, 'output_path': 'artifacts/validated_dataset.json'},
            {'csv_file': text}, {'csv_file': 'fixtures/source.csv'})
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise ContractError('csv_validation_failed', str(exc)) from exc
    dataset = result['validated_dataset']
    for name in dataset['columns']: ident(name)
    for row in dataset['rows']:
        for value in row.values(): literal(value)
    return result


def check_resource(resource):
    if (set(resource) != {'driver', 'engine', 'database', 'schema'}
            or resource['driver'] != VERSION or resource['engine'] != 'postgresql'
            or resource['database'] != 'p2sf_controls'):
        raise ContractError('unsupported_database_resource', 'Require the declared local control database; no URI or production connection')
    ident(resource['schema'])


def write_dataset(database, resource, table, dataset, mode):
    check_resource(resource)
    if mode not in ('append', 'replace'):
        raise ContractError('unsupported_write_mode', 'This explicit subset supports append and replace only')
    schema, target = ident(resource['schema']), ident(table)
    columns = dataset['columns']
    if not columns or len(set(columns)) != len(columns): raise ContractError('invalid_columns', 'Require unique named columns')
    names = ','.join(ident(c) for c in columns)
    rows = dataset['rows']
    if any(set(r) != set(columns) for r in rows): raise ContractError('invalid_dataset', 'Dataset row columns disagree')
    exists = database.scalar('SELECT to_json(to_regclass(' + literal(schema + '.' + target) + ') IS NOT NULL)')
    if exists:
        actual = database.scalar('SELECT coalesce(json_agg(json_build_array(column_name,data_type) ORDER BY ordinal_position),\'[]\'::json) '
            'FROM information_schema.columns WHERE table_schema=' + literal(resource['schema']) + ' AND table_name=' + literal(table))
        if actual != [[c, 'text'] for c in columns]:
            raise ContractError('target_schema_mismatch', 'Existing target columns/types/order differ; nothing is altered')
    statement = 'BEGIN; SET LOCAL standard_conforming_strings=on;\n'
    statement += 'CREATE TABLE IF NOT EXISTS ' + schema + '.' + target + '(' + ','.join(ident(c) + ' TEXT NOT NULL' for c in columns) + ');\n'
    if mode == 'replace': statement += 'DELETE FROM ' + schema + '.' + target + ';\n'
    if rows:
        values = ','.join('(' + ','.join(literal(r[c]) for c in columns) + ')' for r in rows)
        statement += 'INSERT INTO ' + schema + '.' + target + '(' + names + ') VALUES ' + values + ';\n'
    statement += 'COMMIT;'
    database.sql(statement)
    return {'success': True, 'errors': [], 'rows_read': len(rows), 'rows_written': len(rows),
            'write_mode': mode, 'target_table': table, 'target_schema': resource['schema'], 'backend': VERSION}


def load_snapshot(database, resource, raw, parameters):
    if set(parameters) != {'import_spec', 'load_mode', 'has_header', 'delimiter'} or parameters['has_header'] is not True or parameters['delimiter'] != ',':
        raise ContractError('unsupported_import_parameters', 'Explicit headered comma-separated append/replace subset required')
    if set(parameters['import_spec']) != {'target_table'}:
        raise ContractError('unsupported_import_spec', 'Only an explicit target_table is implemented; no inferred mappings')
    dataset = validated(raw, [], fail_on_empty=False)['validated_dataset']
    status = write_dataset(database, resource, parameters['import_spec']['target_table'], dataset, parameters['load_mode'])
    return {'target_database_reference': {'database': resource['database'], 'schema': resource['schema'],
            'table': parameters['import_spec']['target_table']}, 'load_status': status}


def load_tabular(database, resource, workspace, metadata, parameters):
    if set(parameters) != {'target_table', 'write_mode'}:
        raise ContractError('unsupported_tabular_parameters', 'Require explicit target_table and write_mode')
    if metadata.get('contract_version') != 'p2sf-tabular-object/1' or not isinstance(metadata.get('dataset_ref'), str):
        raise ContractError('missing_dataset_reference', 'No guessed source URI or dataset path is permitted')
    path = inside(workspace, metadata['dataset_ref']); raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata.get('dataset_sha256'):
        raise ContractError('dataset_hash_mismatch', 'Bound validated dataset bytes differ from their receipt')
    dataset = json.loads(raw)
    if (metadata.get('success') is not True or dataset.get('valid') is not True
            or metadata.get('record_count') != len(dataset['rows'])
            or metadata.get('columns') != dataset['columns'] or metadata.get('row_count') != len(dataset['rows'])
            or dataset['row_count'] != len(dataset['rows'])):
        raise ContractError('dataset_metadata_mismatch', 'Bound dataset metadata disagrees with its contents')
    return {'load_status': write_dataset(database, resource, parameters['target_table'], dataset, parameters['write_mode'])}


def execute_control(database, resource, workspace, raw, contract, *, mode='replace', fail_on_empty=True, metadata_defect=False):
    """New public three-stage mechanism control, never a recovered model IR."""
    events = []
    workspace = Path(workspace); fixtures = workspace / 'fixtures'; fixtures.mkdir(parents=True, exist_ok=True)
    artifacts = workspace / 'artifacts'; artifacts.mkdir(parents=True, exist_ok=True)
    source = fixtures / 'source.csv'
    if raw is not None: source.write_bytes(raw)
    detected = file_base.sensor({'location_type': 'filesystem', 'path': 'source.csv', 'availability_condition': 'exists'},
        {'driver': 'fixture-filesystem', 'root': '.'}, fixtures)
    for port, value in detected.items(): (artifacts / (port + '.json')).write_bytes(canonical_bytes(value))
    if not detected['availability_decision']['available']:
        return {'state': 'skipped_missing_input', 'events': [{'stage': 'detect', 'available': False}], 'loader_called': False}
    events.append({'stage': 'detect', 'available': True})
    raw = source.read_bytes()
    validated_outputs = validated(raw, contract['required_columns'], fail_on_empty=fail_on_empty)
    (artifacts / 'validation_status.json').write_bytes(canonical_bytes(validated_outputs['validation_status']))
    dataset_bytes = canonical_bytes(validated_outputs['validated_dataset'])
    (artifacts / 'validated_dataset.json').write_bytes(dataset_bytes)
    metadata = {**validated_outputs['validated_data_object'], 'contract_version': 'p2sf-tabular-object/1',
                'dataset_ref': 'artifacts/validated_dataset.json', 'dataset_sha256': hashlib.sha256(dataset_bytes).hexdigest()}
    if metadata_defect: metadata['dataset_sha256'] = '0' * 64
    (artifacts / 'validated_data_object.json').write_bytes(canonical_bytes(metadata))
    events.append({'stage': 'validate', 'success': True})
    service = contract['loader_service']
    if service == SNAPSHOT:
        result = load_snapshot(database, resource, raw, {'import_spec': {'target_table': contract['target_table']},
            'load_mode': mode, 'has_header': True, 'delimiter': ','})
    elif service == TABULAR:
        result = load_tabular(database, resource, workspace, metadata,
            {'target_table': contract['target_table'], 'write_mode': mode})
    else: raise ContractError('unregistered_loader', 'No registered load operation')
    for port, value in result.items(): (artifacts / (port + '.json')).write_bytes(canonical_bytes(value))
    events.append({'stage': 'load', 'success': True})
    return {'state': 'loaded', 'events': events, 'loader_called': True, **result}
