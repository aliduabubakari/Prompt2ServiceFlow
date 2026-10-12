#!/usr/bin/env python3
"""Normalize: compute quality scores, flag parameter deviations, assign grades."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def in_range(val, lo, hi):
    if val is None: return None
    if lo is not None and val<lo: return False
    if hi is not None and val>hi: return False
    return True

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    staged=json.loads((art/"stage_raw_artifacts_artifact.json").read_text(encoding="utf-8"))
    grades=ingested["thresholds"]["quality_grades"]
    normalized=[]
    for s in staged["staged"]:
        issues=[]
        ps_ok=in_range(s.get("pixel_spacing"),s.get("ref_pixel_spacing_min"),s.get("ref_pixel_spacing_max"))
        st_ok=in_range(s.get("slice_thickness"),s.get("ref_slice_thickness_min"),s.get("ref_slice_thickness_max"))
        kvp_ok=in_range(s.get("kvp"),s.get("ref_kvp_min"),s.get("ref_kvp_max"))
        img_ok=s.get("image_count",0)>= (s.get("ref_min_images") or 0)
        if ps_ok is False: issues.append(f"pixel_spacing_out_of_range: {s.get('pixel_spacing')}")
        if st_ok is False: issues.append(f"slice_thickness_out_of_range: {s.get('slice_thickness')}")
        if kvp_ok is False: issues.append(f"kvp_out_of_range: {s.get('kvp')}")
        if not img_ok: issues.append(f"insufficient_images: {s.get('image_count')}")
        n_issues=len(issues)
        if n_issues<=grades["pass"]["max_issues"]: grade="pass"
        elif n_issues<=grades["warning"]["max_issues"]: grade="warning"
        else: grade="fail"
        normalized.append({"study_uid":s["study_uid"],"patient_id":s["patient_id"],"modality":s["modality"],
                           "body_part":s["body_part"],"image_count":s["image_count"],"quality_grade":grade,
                           "issue_count":n_issues,"issues":issues})
    (art/"normalize_records_artifact.json").write_text(json.dumps({"normalized":normalized,"total":len(normalized)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_records_status.json").write_text(json.dumps({"success":True,"normalized":len(normalized),"pass":sum(1 for n in normalized if n["quality_grade"]=="pass"),"warning":sum(1 for n in normalized if n["quality_grade"]=="warning"),"fail":sum(1 for n in normalized if n["quality_grade"]=="fail"),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
