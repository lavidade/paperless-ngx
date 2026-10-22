# Container build and release workflow

The `release/2.7` branch contains build configuration for Paperless 2.7.2
with shared archive serial numbers. It does not include an upstream upgrade.

## Versioning

- Branch pushes publish unique candidate tags:
  `2.7.2-lavida-build.<run-id>.<attempt>.<commit>`.
- Approved version tags follow `v2.7.2-lavida.N`; the container workflow
  publishes the corresponding image and a GitHub release with its digest.
- Existing image and Git tags must not be overwritten or moved. The next
  release number must be selected after checking existing published versions.
- The workflow does not publish `latest` and never deploys the application.

## Release procedure

1. Review the source changes and the candidate workflow result.
2. Run application regression tests in an isolated environment, including
   repeated ASN, consumer/barcode behavior, OCR and search. Use synthetic
   fixtures and isolated service endpoints.
3. After approval, create a new annotated version tag on the reviewed commit.
4. Verify the workflow result, image digest and published platforms.
5. Treat deployment as a separate, explicitly authorized operation.

The build targets AMD64 and ARM64. Dependencies and base images may change
between builds; a rebuilt image is not guaranteed to be byte-identical to
an older artifact. A successful build alone is not application acceptance.
Application regression tests are separate from container publication.

Use repository-scoped Actions credentials for publication, not personal
administrator tokens embedded in workflow files. Grant registry access using
least privilege and never commit real credentials or deployment configuration.
