"""Reuse the actual method controllers with a shared, declared v2 boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil

from prompt2serviceflow.experiments import methods as original_methods
from prompt2serviceflow.experiments import prompts as original_prompts
from prompt2serviceflow.experiments import agentic as original_agentic
import semantic_public_tools as public


def common_context(workspace):
    return '\n\n# Shared v2 public execution contract\n' + (Path(workspace) / public.CONTRACT).read_text()


def method_module(workspace):
    """Independent module namespaces; never mutate published method globals."""
    module = public.clone_module(original_methods, '_p2sf_v2_actual_methods')
    prompts = public.clone_module(original_prompts, '_p2sf_v2_actual_prompts')
    prompts.PROMPT_VERSION = 'v2.public-real.1'
    old_sentence = 'All runtime scripts are deterministic mocks over supplied fixtures; they '
    if prompts.SYSTEM_BASE.count(old_sentence) != 1:
        raise ValueError('Original system template changed; review v2 integration')
    prompts.SYSTEM_BASE = prompts.SYSTEM_BASE.replace(old_sentence,
        'Runtime scripts perform registered real calculations over supplied fixtures; they ')
    original_generate, original_repair = prompts.m3_ir_prompts, prompts.m4_repair_prompts
    def generate(view, manifest):
        system, user = original_generate(view, manifest)
        user = user.replace('the runtime manifest, mock scripts, and Argo resources from this IR;',
                            'the real runtime manifest, registered service scripts, and Argo resources from this IR;')
        start = user.index('- For the source block, use:')
        end = user.index('Output one valid JSON object only', start)
        user = user[:start] + '- Use the exact public bookkeeping provided in the v2 contract below.\n' + user[end:]
        return system, user + common_context(workspace)
    def repair(*args, **kwargs):
        system, user = original_repair(*args, **kwargs)
        return system, user + common_context(workspace)
    prompts.m3_ir_prompts, prompts.m4_repair_prompts = generate, repair
    module.prompts = prompts
    module.materialize_runtime = public.materialize_runtime
    module.validate_submission = public.validate_submission
    return module


def agent_module(decoding=None):
    """Unchanged Pi controller/tool protocol; versioned tools and image payload."""
    module = public.clone_module(original_agentic, '_p2sf_v2_actual_agentic')
    module.AGENT_IMAGE_TAG = 'p2sf-v2-real-agent'
    module.PROXY_IMAGE_TAG = 'p2sf-v2-real-proxy'
    module.M5_VERSION = 'v2.27.1'
    module.M5_PROMPT_VERSION = 'v2.public-real.1'
    module.RUNTIME_COMPILER_VERSION = public.VERSION
    module.prompts = public.clone_module(original_prompts, '_p2sf_v2_pi_prompts')
    module.prompts.PROMPT_VERSION = 'v2.public-real.1'
    template = module.METHOD_TEMPLATE
    start = template.index('- Use the exact source identity recorded by `workspace.yaml`:')
    end = template.index('- Evidence source must be', start)
    template = template[:start] + '- Use the exact source, catalog and composition metadata in `v2_contract.json`.\n' + template[end:]
    template = template.replace('It deterministically regenerates `submission/runtime/` and `submission/argo/`',
        'It applies the shared declared completion rules and deterministically regenerates `submission/runtime/` and `submission/argo/`')
    module.METHOD_TEMPLATE = template + ('\n## Shared v2 public execution contract\n'
        'Read `v2_contract.json` before composing. It contains exactly the same numerical rules, '
        'registered operations, input role, public metadata and compiler-completion policy supplied '
        'to M3 and M4. The runtime performs real local calculations, with no production service contact.\n')
    stage = module.stage_agent_workspace
    def staged(*args, **kwargs):
        root = stage(*args, **kwargs)
        for name, action in [('compile', 'compile'), ('.validate_submission_real', 'validate')]:
            target = root / 'bin' / name
            target.write_text('#!/usr/bin/env python3\nimport sys\nsys.path.insert(0,"/opt/p2sf/v2")\n'
                'from semantic_public_tools import main\nraise SystemExit(main([' + repr(action) + ',*sys.argv[1:]]))\n')
            target.chmod(0o755)
        return root
    module.stage_agent_workspace = staged
    prepare_image = module.prepare_image_context
    def image_context(context):
        prepare_image(context)
        # pyproject references these packaging files; no paper or evaluator is
        # copied into the container image or agent workspace.
        for name in ('README.md', 'LICENSE'):
            source = module.REPO_ROOT / name
            if source.is_file(): shutil.copy2(source, context / 'pkg' / name)
        dockerfile = context / 'Dockerfile'
        text = dockerfile.read_text().replace('COPY pkg/src ./src', 'COPY pkg/src ./src\nCOPY pkg/README.md ./README.md\nCOPY pkg/LICENSE ./LICENSE')
        text = text.replace('COPY agent_driver.mjs /opt/p2sf/agent_driver.mjs',
            'COPY agent_driver.mjs /opt/p2sf/agent_driver.mjs\nCOPY v2 /opt/p2sf/v2\nRUN pip install --no-cache-dir PyYAML==6.0.2 jsonschema==4.24.0')
        dockerfile.write_text(text)
        (context / 'v2').mkdir()
        for name, source in public.deployment_sources().items():
            (context / 'v2' / (name + '.py')).write_text(source)
    module.prepare_image_context = image_context
    prepare_proxy = module.prepare_proxy_context
    def proxy_context(context):
        prepare_proxy(context)
        path = context / 'proxy.py'
        text = path.read_text()
        marker = '        body = self.rfile.read(length)\n'
        if text.count(marker) != 1:
            raise ValueError('Original proxy changed; review versioned decoding/recording patch')
        text = text.replace(marker, marker +
            '        document = json.loads(body)\n'
            '        settings = json.loads(os.environ.get("P2SF_DECODING", "{}"))\n'
            '        for key in ("temperature", "top_p", "seed", "max_tokens"):\n'
            '            if key in settings: document[key] = settings[key]\n'
            '        body = json.dumps(document).encode()\n'
            '        _log({"event":"request_wire", "request":json.loads(body.decode().replace(UPSTREAM_API_KEY,"<redacted>"))})\n')
        marker = '        usage = _extract_usage_from_sse(payload)\n'
        if text.count(marker) != 1:
            raise ValueError('Original proxy response point changed')
        text = text.replace(marker, '        _log({"event":"response_wire", "body":payload.decode("utf-8",errors="replace").replace(UPSTREAM_API_KEY,"<redacted>")})\n' + marker)
        path.write_text(text)
    module.prepare_proxy_context = proxy_context
    docker = module._docker
    def configured_docker(*args, **kwargs):
        if args and args[0] == 'run' and args[-1] == module.PROXY_IMAGE_TAG + ':' + module.M5_VERSION:
            if decoding is None:
                raise ValueError('Explicit shared decoding settings required for M5 inference')
            args = (*args[:-1], '-e', 'P2SF_DECODING=' + json.dumps(decoding, separators=(',', ':')), args[-1])
        return docker(*args, **kwargs)
    module._docker = configured_docker
    module.validate_submission = public.validate_submission
    # Suppress the unchanged paper's private scorer entirely. The new runner
    # evaluates only after the agent terminates, outside its mounted workspace.
    module.score_submission = lambda *args, **kwargs: {'summary': {'status': 'v2_evaluator_deferred'}}
    return module
