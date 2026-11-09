"""Same conservative completion algorithm, registered relational publisher."""
from __future__ import annotations

import importlib.util
import sys
import semantic_completion as previous


def validate_contract(contract):
    rule = {'service_id': 'api_table_output_bundle_publisher', 'service_version': '1.0.0',
            'operation_profile': 'publish_outputs', 'port': 'output_artifacts', 'artifact_role': 'report',
            'artifact_data_types': ['json', 'object'], 'projection': 'publication_audit_manifest',
            'maximum_auxiliary_reports': 1, 'require_declared_intent_output': True, 'require_no_consumers': True}
    if contract.get('projection_contract_version') != 'p2sf.public-relational-projections/1' or contract.get('profile_version') != 'relational-routing-1' or contract.get('rules') != [rule]:
        raise ValueError('No registered relational projection implementation')


spec = importlib.util.spec_from_file_location('_p2sf_relational_completion', previous.__file__)
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
module.validate_contract = validate_contract
complete, verify_protected = module.complete, module.verify_protected
