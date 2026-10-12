# Catalog Curation Policy 0.1.0

Version `0.1.0` uses a hybrid distractor strategy.

## Core Strategy

Contextual distractors selected from the 129 required services remain the
primary benchmark challenge. They are grounded in real capability overlap,
format differences, target-system differences, missing outputs, contracts, and
policies observed in the main 40-pipeline corpus.

The release does not create one synthetic variant for every required service.
That would inflate the catalog, make many alternatives mechanically obvious,
and complicate review without improving service-discovery validity.

## Supplemental Pool

Eight reviewed services fill gaps in the contextual registry:

- three deprecated compatibility services;
- three experimental policy-risk services;
- two controlled generic escape hatches.

The services are model-visible and contain honest lifecycle, policy,
limitation, and replacement metadata. Gold and distractor labels remain only
in the private candidate-relationship file.

## Candidate-Set Rules

- Candidate-set IDs are globally namespaced by split, pipeline, and required
  service.
- Every required service has exactly one candidate set.
- Every set contains exactly one gold service.
- Every set contains between three and six distinct candidates.
- Curation adds at most one supplemental candidate to a set.
- Supplemental candidates are added only when capability, lifecycle, or
  policy overlap is defensible.
- Generic escape hatches must not become gold services in `0.1.0`.

## Release Outcome

The curated development-corpus catalog contains:

- 129 required services;
- 8 supplemental services;
- 137 total services;
- 153 globally unique candidate sets;
- 138 supplemental candidate relations.

The generated report at
`runs/catalog_generation/gpt55-catalog-v001/reports/catalog_curation.json`
records every ID normalization and supplemental relation.

## Future Versions

Later versions may add targeted deprecated versions or policy variants when
error analysis identifies a weak capability family. Additions should be
review-driven rather than produced as a full Cartesian expansion of the
catalog.
