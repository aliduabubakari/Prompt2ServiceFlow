"""Tests for diagnostic denominators and output checks, without model calls."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import analyze_v2_corpus_assertion_results as analysis


def test_format_and_field_errors_remain_failed_assertions():
    assert analysis.reason({'status':'evaluation_error','message':'JSONDecodeError: bad'})=='output_not_valid_json'
    assert analysis.reason({'status':'evaluation_error','message':"KeyError: 'success'"})=='missing_json_field'
    assert analysis.reason({'status':'unscored_role_unresolved','message':'missing role'})=='unresolved_output_role'


def test_output_presence_does_not_imply_parseability(tmp_path):
    (tmp_path/'result.txt').write_text('example\n')
    row=analysis.positive_output(tmp_path,'artifacts/original.json',{'result.txt'},{'json_path_equals'})
    assert row['state']=='present_nonempty' and row['valid_json'] is False


def test_unresolved_paths_cannot_select_an_existing_good_output(tmp_path):
    (tmp_path/'good.json').write_text('{"success":true}')
    row=analysis.positive_output(tmp_path,'artifacts/original.json',{None,'good.json'},{'json_path_equals'})
    assert row['state']=='unresolved' and row['valid_json'] is None


def test_full_roster_is_distinct_from_conditional_success():
    rows=[{'id':f'{task}/{seed}','model':'example','method':'m4','case':f'main/task{task}',
        'replayed':task==0,'complete_execution':task==0,'original_pass':False,'literal_pass':False,'role_pass':task==0}
        for task in range(110) for seed in range(3)]
    result=analysis.summarize(rows)[0]
    assert result['declared']==330 and result['replayed']==3 and result['role_passes']==3
    assert result['role_pass_given_replay']==1 and abs(result['role_pass_rate']-1/110)<1e-10
