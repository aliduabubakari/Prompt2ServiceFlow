# Repository release checklist

Complete these items before the first public push or archival release:

- [ ] Replace `OWNER` in `CITATION.cff` with the actual GitHub owner.
- [ ] Add the final paper title, author list, venue, year, and DOI when assigned.
- [ ] Confirm that the six frozen publication configurations match the paper.
- [ ] Run `make verify-results`, `make verify-analysis`, and `make test` in a clean clone.
- [ ] Confirm that no API token, authorization header, `.env` file, or private endpoint credential is staged.
- [ ] Confirm that no file exceeds GitHub’s per-file limit; keep manifests and scores in Git and publish the fuller run records as release assets.
- [ ] Deposit the untouched raw run tree in a GitHub Release or Zenodo and add its URL/DOI and SHA-256 checksum to the main README.
- [ ] Tag the release used by the paper, for example `paper-v1.0.0`.
- [ ] Archive that tag and record its commit SHA in the paper’s artifact-availability statement.

Do not rewrite a published freeze or replace a published batch summary. Corrections should create a new version with a short provenance note.

