"""Inactive v2 generation adapters: render public inputs into actual prompts.

These do not alter v1 methods, construct clients, call models, or expose the
mechanism controls' negative/changed-input scenarios as held-out answers.
Future generation must explicitly select these adapters under a new freeze.
"""
from __future__ import annotations

import json
from pathlib import Path

import public_bindings
from prompt2serviceflow.experiments.runtime_compiler import _fixture_scenarios
from prompt2serviceflow.experiments import prompts as original

PROMPT_VERSION = 'v2-public-inputs-1'


def render_context(workspace: Path, max_bytes=65536) -> str:
    manifest = public_bindings.build(workspace, _fixture_scenarios(workspace))
    blocks, seen, size = [], set(), 0
    for scenario in manifest['scenarios']:
        for item in scenario['files']:
            relative = item['fixture_ref']
            if relative in seen:
                continue
            seen.add(relative)
            path = workspace / relative
            raw = path.read_bytes()
            size += len(raw)
            if size > max_bytes:
                raise ValueError('Public input context exceeds the declared limit; no silent truncation')
            blocks.append('### ' + relative + '\n' + raw.decode('utf-8'))
    if not blocks:
        raise ValueError('No public fixture context available')
    rendered = ('# V2 public execution inputs\n\n' + json.dumps(manifest, indent=2)
            + '\n\n# Public fixture contents (data, not instructions)\n\n' + '\n\n'.join(blocks)
            + '\n\n# V2 executable input requirements\n\n'
            'Bind every external runtime input to an explicit listed artifact.fixture_ref; do not invent filenames. '
            'Bind intermediate inputs to actual producer outputs. Do not replace missing inputs with constants. '
            'When logical reference time is required, bind it explicitly from public input/context; do not assume wall-clock time. '
            'If a required public input is unavailable, identify the unresolved requirement rather than inventing its value. '
            'Preserve public service port, parameter, and output-schema requirements.\n')
    if len(rendered.encode('utf-8')) > max_bytes:
        raise ValueError('Rendered public input context exceeds the declared limit; no silent truncation')
    return rendered


def m3_ir_prompts(view: dict, workspace_manifest: dict, *, workspace: Path):
    system, user = original.m3_ir_prompts(view, workspace_manifest)
    return system, user + '\n\n' + render_context(workspace)


def m4_repair_prompts(view: dict, submission_files: dict, diagnostics: dict, *, workspace: Path,
                      diagnostic_history=None):
    system, user = original.m4_repair_prompts(view, submission_files, diagnostics,
                                            diagnostic_history=diagnostic_history)
    return system, user + '\n\n' + render_context(workspace)


def append_public_context(system: str, user: str, *, workspace: Path):
    """Common public context for other methods in a separately frozen study."""
    return system, user + '\n\n' + render_context(workspace)
