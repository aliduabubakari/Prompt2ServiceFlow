#!/usr/bin/env python3
"""Validate: required fields, year range, study type, abstract length."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    articles,criteria=ingested["articles"],ingested["criteria"]
    excluded=set(criteria["excluded_study_types"]); max_age=criteria["max_article_age_years"]
    cur=criteria["current_year"]; min_words=criteria["min_abstract_words"]; req_full=criteria["require_full_text"]
    req_kw=set(criteria["required_keywords"]); required={"article_id","title","year","study_type"}
    errors=[]; valid=[]
    for article in articles:
        issues=[]
        if required-set(article.keys()): issues.append(f"missing_fields: {required-set(article.keys())}")
        if article.get("study_type") in excluded: issues.append(f"excluded_study_type: {article.get('study_type')}")
        if cur-article.get("year",cur)>max_age: issues.append(f"too_old: {article.get('year')}")
        if article.get("abstract_word_count",0)<min_words: issues.append(f"abstract_too_short: {article.get('abstract_word_count')}<{min_words}")
        if req_full and not article.get("has_full_text"): issues.append("full_text_missing")
        kw_match=bool(set(article.get("keywords",[]))&req_kw)
        if not kw_match: issues.append("no_matching_keywords")
        if issues: errors.append({"article_id":article.get("article_id","?"),"issues":issues})
        else: valid.append(article)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
