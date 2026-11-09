# Exact semantic-audit implementation snapshot

This isolated source tree contains the actual profile-38.1 public compiler,
execution-evidence kernel, evaluator, original runners, controls, configurations
and their dependent audit modules. It does not replace the original generation
implementation under the main src/ directory. SOURCE_SHA256.json identifies the
copied historical bytes. Frozen profile implementation hashes remain unchanged.

For portable, no-execution result reproduction, use the main repository's
scripts/reproduce_posthoc_results.py and the content-addressed evidence bundle.
It verifies the original seals and hashes without rewriting absolute paths.
The original native analysis was also rerun on the author workspace and passed.

The original runtime runner is scripts/run_v2_execution_evidence_replay_v2.py;
its profile is audit/v2/execution_evidence_profile.v1.json and protocol freeze
is audit/v2/execution_evidence_replay.freeze.v2.json. Its original path-pinned
runtime replay requires restoration of the archived data environment and the
supported execution sandbox; the portable statistics reader does not execute it.
A fresh relocated runtime execution was not performed in this preparation.
