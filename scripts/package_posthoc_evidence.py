#!/usr/bin/env python3
"""Preserve the sealed post-hoc evidence in a relocatable content-addressed store.

Only local files are written. Source records and embedded historical paths are
not rewritten; a separate root map resolves their identities after extraction.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--semantic-root", type=Path, required=True)
    p.add_argument("--original-root", type=Path, required=True)
    p.add_argument("--package", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    semantic, original, output = a.semantic_root.resolve(), a.original_root.resolve(), a.output.resolve()
    if output.exists():
        raise SystemExit("Preserve the previous bundle; choose a new output directory")
    source = semantic / "audit/evaluator_only" / a.package
    run = json.loads((source / "run.json").read_text())
    pins = json.loads((source / "input_sha256.json").read_text())
    seal = json.loads((source / "output_sha256.json").read_text())
    assert fingerprint(pins) == run["input_fingerprint"]
    assert fingerprint(seal["files"]) == seal["output_fingerprint"]
    assert run["status"] == "complete" and run["source_inputs_unchanged"]
    assert run["reference_gate"]["pass"] and run["llm_calls"] == 0
    output.mkdir(parents=True)
    (output / "blobs").mkdir()
    files, objects = {}, set()

    def logical(path):
        path = path if path.is_absolute() else semantic / path
        for label, root in (("semantic", semantic), ("original", original)):
            if path.is_relative_to(root):
                return label + "/" + path.relative_to(root).as_posix(), path
        raise ValueError(f"Unmapped source root: {path}")

    def add(path, expected=None):
        name, path = logical(Path(path))
        if expected == "MISSING":
            if path.exists():
                raise ValueError(f"Recorded absence changed: {name}")
            files[name] = expected
            return
        if expected and expected in objects:
            if name in files and files[name] != expected:
                raise ValueError("Conflicting frozen versions of " + name)
            files[name] = expected
            return
        data = path.read_bytes()
        value = hashlib.sha256(data).hexdigest()
        if expected and value != expected:
            raise ValueError("Pinned source changed: " + name)
        if name in files and files[name] != value:
            raise ValueError("Conflicting frozen versions of " + name)
        files[name] = value
        if value not in objects:
            (output / "blobs" / value).write_bytes(data)
            objects.add(value)

    for path, expected in pins.items():
        add(path, expected)
    for name, expected in seal["files"].items():
        add(source / name, expected)
    add(source / "output_sha256.json")
    manifest = {"format": "p2sf-content-addressed-evidence/1", "package": a.package,
                "historical_roots": {"semantic": str(semantic), "original": str(original)},
                "files": files, "file_map_fingerprint": fingerprint(files),
                "sealed_output_fingerprint": seal["output_fingerprint"],
                "input_fingerprint": run["input_fingerprint"],
                "input_pin_count": len(pins), "sealed_output_files": len(seal["files"]),
                "unique_objects": len(objects), "scope": "Exact original bytes; no inference or runtime replay"}
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: value for key, value in manifest.items() if key not in {"files", "historical_roots"}}, indent=2))


if __name__ == "__main__":
    main()
