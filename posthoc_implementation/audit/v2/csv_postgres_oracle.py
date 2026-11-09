"""Independent CSV-reader expectations and read-only PostgreSQL observation."""
from __future__ import annotations

from collections import Counter
import csv
import io
import re


def identifier(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', value): raise ValueError('Unsafe observation identifier')
    return '"' + value + '"'


def observe(database, schema, table):
    # This reader is separate from the loader and never consumes its status
    # or in-memory dataset to reconstruct database contents.
    relation = identifier(schema) + '.' + identifier(table)
    present = database.scalar("SELECT to_json(to_regclass('" + relation + "') IS NOT NULL)")
    if not present: return {'exists': False, 'columns': [], 'types': [], 'rows': []}
    cols = database.scalar("SELECT json_agg(json_build_array(column_name,data_type) ORDER BY ordinal_position) "
        "FROM information_schema.columns WHERE table_schema='" + schema + "' AND table_name='" + table + "'")
    names = [c[0] for c in cols]
    rows = database.scalar("SELECT coalesce(json_agg(json_build_array(" + ','.join(identifier(c) for c in names) + ")), '[]'::json) FROM " + relation)
    return {'exists': True, 'columns': names, 'types': [c[1] for c in cols], 'rows': rows}


def expected_csv(raw):
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8')), delimiter=',', strict=True))
    if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows[1:]): raise ValueError('Invalid expected CSV shape')
    return rows[0], rows[1:]


def check_loaded(snapshot, raw, status, *, repetitions=1):
    names, rows = expected_csv(raw)
    checks = {'real_target_exists': snapshot['exists'], 'column_names_and_order': snapshot['columns'] == names,
        'declared_text_schema': snapshot['types'] == ['text'] * len(names),
        'all_persisted_values_and_multiplicity': Counter(map(tuple, snapshot['rows'])) == Counter(map(tuple, rows * repetitions)),
        'reported_write_count': status.get('success') is True and status.get('rows_written') == len(rows)}
    return {'pass': all(checks.values()), 'checks': checks}


def same_state(before, after):
    return (all(before[k] == after[k] for k in ('exists', 'columns', 'types'))
            and Counter(map(tuple, before['rows'])) == Counter(map(tuple, after['rows'])))
