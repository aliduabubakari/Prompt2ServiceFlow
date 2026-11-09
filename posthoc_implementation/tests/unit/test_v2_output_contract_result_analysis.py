"""Post-hoc analysis classification and full-roster denominator controls."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import analyze_v2_output_contract_results as analysis


def test_known_output_errors_are_not_hidden_as_infrastructure():
    assert analysis.reason({'status':'fail','message':'output_format_error: invalid JSON'})=='output_not_valid_json'
    assert analysis.reason({'status':'fail','message':'missing_output_field: success'})=='missing_json_field'
    assert analysis.reason({'status':'evaluation_error','message':"ValueError: invalid literal for int() with base 10: 'tables'"})=='json_path_container_type_mismatch'


def test_comparison_retains_all_three_repetitions_and_unreplayed_cells():
    rows=[{'model':'example','method':'m4','case':f'task{task}','replayed':task==0,'complete_execution':task==0,
        'original_pass':False,'literal_pass':False,'role_pass':task==0,'baseline_role_pass':task==0 and seed==0}
        for task in range(110) for seed in range(3)]
    row=analysis.summarize(rows)[0]
    assert row['declared']==330 and row['replayed']==3
    assert row['baseline_role_passes']==1 and row['role_passes']==3
    assert row['gained_baseline_to_role']==2 and row['lost_baseline_to_role']==0
    assert abs(row['role_pass_rate']-1/110)<1e-10 and row['role_pass_given_replay']==1
