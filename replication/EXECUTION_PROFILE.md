# Execution conditions and their evidence

1. Original generation/public validity: frozen primary and ablation records.
2. Original Main-40 scenario-name/scorer correction: saved scorer-1.2.1 audit.
3. Revised replay protocol `38.1.0`, profile `fixture-execution-evidence/1`:
   compiler and evaluator intervention on unchanged saved IRs under public
   file-backed mock execution.

The replay changes mock-output construction, public fixture access, dependency
scheduling, producer-specific storage and output-role resolution. It observes
public fixture hashes, record counts and declared producer dependencies under
controlled mock execution. Held-out predicates and expected values remain
fixed and are excluded from generation and the public compiler. The evaluator
can select different artifact paths for the same assertion. All 2,970 original
identities remain in denominators; missing, originally invalid and unsupported
cases are non-passes. Of 797 originally public-valid cases, 781 have supported
execution and 16 are blocked. The reference profile gate passes for all 110
references, but only 73 satisfy every held-out assertion; these are distinct checks.

Implementation: posthoc_implementation/. Frozen public profile and source
checksums are included there. Raw records are preserved byte-for-byte in the
content-addressed archive. Its manifest maps historical paths without modifying
sealed JSON, fixtures, IRs, compiled runtime programs or assertion snapshots.

Offline: scripts/reproduce_posthoc_results.py --evidence-root POSTHOC_DIR --out OUTPUT
It verifies input pins, output seals, cell identities, retained IR hashes,
reference controls and state reconciliation, then regenerates rates and BCa CIs.
No model calls or runtime programs are executed by this route.

Actual replay: the original runner under posthoc_implementation/scripts/ and
its authored positive/negative controls are supplied. This needs restoration of
the data environment and original sandbox; relocated runtime execution is a
separate qualification, not implied by saved-results verification.

The exact profile and protocol pins are in
`posthoc_implementation/audit/v2/execution_evidence_profile.v1.json` and
`execution_evidence_replay.freeze.v2.json` in that directory. The Table 6
and paired CSVs use the corrected original G6-Assert results as the original
comparator. Missing-output messages describe recorded symptoms. The bundled
runtime and evaluator changes prevent attribution of gains to any one change.
