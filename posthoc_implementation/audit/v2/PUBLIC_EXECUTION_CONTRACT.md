# Public execution contract — v2 candidate

Contract version: `2.0.0`.
Package candidate: `2.0.0-candidate.1`.
Status: local development; not a new publication or replacement for v1.

## 1. Inputs must be executable, not guessed

A public `public_execution_inputs.json` lists each active scenario, its fixture
root, and available public files with relative paths, sizes, and SHA-256 hashes.
It contains availability information only: it does not choose which file
fulfills a service's purpose and does not include expected outputs.

An external input must have an explicit binding. For these reference controls,
the existing IR's `artifact.fixture_ref` supplies it. The runtime does not
select a similarly named file, infer a binding from gold answers, or replace
an upstream result with a mock or a reference output.

The unchanged legacy convention is explicit here:

- `fixtures/inputs/<path>` means `<path>` under the active scenario fixture root.
- `fixtures/scenarios/<name>/<path>` also supplies an active-scenario-relative
  `<path>`. This preserves the earlier resolver convention; the named directory
  is not an instruction to read a different scenario's fixture.
- The resolved file must be listed for every active scenario in the public
  manifest. Resolution never escapes the scenario root.
- Other reference forms are unsupported in this candidate, not automatically
  model errors. Missing mappings are not added to saved compositions.
- Inputs produced by another service require an implemented producer. These
  isolated controls do not provide substitute upstream data.
- Logical reference time must be explicitly bound when an operation needs it.
  No current-time fallback or hidden scenario parameters are introduced.

Optional input ports may be omitted only when the service explicitly permits
that. Required ports must be bound. Descriptors and actual input/output schemas
still determine data compatibility.

This is a stricter execution contract than v1's optional `fixture_ref` schema
alone. A future v2 generation experiment must supply this public information
in the actual rendered prompts and ask for executable input bindings. Merely
adding it to a Python view or an inaccessible folder is insufficient. The
current change does not modify old prompts, require a new generation run, or
pretend that legacy outputs were generated under this contract.

## 2. Output identity and output location are different

Each bound output port has a canonical artifact:

```text
artifacts/<artifact_id>.json
artifacts/<artifact_id>.csv
```

These identities are authoritative for service-to-service bindings. Different
ports cannot overwrite each other's canonical files. Duplicate ports or
artifact identities are rejected before writing.

A service parameter such as CSV loader `output_path` names an additional
logical service output location, not a second binding to an unrelated output
port. The loader's requested location contains the validated **dataset**;
the exporter's `output_filename` contains its **CSV**.

Requested locations are materialized in a separate namespace:

```text
service_outputs/<intent_id>/<output_port>/<absolute|relative>/<logical_path>
```

For example, if a loader uses `output_path=/workspace/artifacts/metadata.json`
while its metadata output binds to artifact `metadata`, then:

- `artifacts/metadata.json` remains the metadata payload.
- The dataset remains at its own canonical bound artifact path.
- `service_outputs/<intent>/validated_dataset/absolute/workspace/artifacts/metadata.json`
  contains the dataset requested by `output_path`.

The distinction is intentional. The public service description calls
`output_path` the dataset location; choosing the metadata port solely because
its filename matches would silently change that meaning. Separate namespaces
preserve both meanings without overwriting either output. This is a documented
v2 runtime convention, not a claim that all v1 implementations already used it.

An absolute location is a logical container label, never a host filesystem
destination. Relative and absolute labels remain distinct. Dot/traversal
segments, ambiguous double slashes, unresolved templates/variables, URIs,
backslashes, and empty/directory-only locations are rejected. No shell
expansion or host path creation occurs.

`logs/public_output_bindings.json` records every port, canonical path,
requested logical location where applicable, contained materialized path,
and content SHA-256. Requested copies must be byte-identical to their
corresponding canonical port payload. Public JSON schemas validate the
computed canonical outputs as before.

## 3. Scope and interpretation

The current adapter roster remains the same three exact service/version pairs
as audit v3. Service computation is not changed to match hidden expected
answers. Typed CSV schema rules and other unsupported operations remain
unsupported. No whole-workflow branching or upstream executor is added.

The new controls cover the four reference CSV invocations that hit the v3
path collision and the two previously passing reference invocations. They
measure input availability, schema-valid actual computation, requested-output
integrity, and changed-input age/count behavior. They are not G6-Assert or
method-performance estimates.

The published v1 code, archived runs, paper scores, and DOI remain unchanged.
Any eventual v2 release needs a reviewed changelog, explicit protocol/model
configuration, new evidence, and its own versioned release. This local
candidate does not publish, tag, upload, or update Zenodo automatically.
