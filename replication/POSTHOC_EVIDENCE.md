# Profile 38.1 evidence layout

MANIFEST.json maps logical original/semantic roots to SHA-256 content addresses.
blobs/<sha256> contains each exact file once. No frozen paths or file bytes are
rewritten. Recorded MISSING values preserve intentional absences. The manifest
fingerprint and archive checksum are pinned in replication/POSTHOC_MANIFEST.json.

This preserves 117,589 source pins and 51,370 sealed output files, including all
model/reference checkpoints, compiled retained IR/runtime programs, execution
reports, fixture hashes, output snapshots, assertion records and source freezes.
The same bytes can have multiple historical names without duplicated storage.
Original raw input files are preserved where the historical audit pinned them;
the older path-normalized archive remains a separate historical component.

The portable reader verifies the original inventories, fingerprints and file
hashes, checks the fixed 2,970-cell roster against the original run records,
and verifies per-cell evidence inventories and unchanged saved IR identities.
It also verifies all reference controls, the 797/781/16 reconciliation and the
full 330-observation method denominators before calculating rates and BCa CIs.

Use the original native source snapshot for implementation inspection; the new
portable reader is a saved-evidence adapter, not a replacement execution kernel.
No new confirmatory significance tests are inferred from the revised profile.
