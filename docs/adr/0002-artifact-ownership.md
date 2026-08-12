# ADR 0002: Artifact ownership and storage

## Decision

Reference polygons, licenses, crosswalks, small fixtures and manifests are
versioned.  Raw downloads are provider/version scoped.  Interim, processed,
cache, generated figures and published bundles remain local artifacts with
checksums and provenance manifests.

## Consequences

- Processed and validation products are scoped by country, city, study and layer.
- Git history is not rewritten; large historical outputs are removed from the
  index only after fixture and parity coverage exists.
- A remote artifact store can later implement the same manifest contract.
