# Lavida Edition releases

This fork adds **Shared ASN**: several documents may use the same archive serial
number. `main` tracks the maintained Paperless-ngx 3.3.3 Lavida source, including
subsequent synthetic test and CI fixes. Historical release tags identify the
source of the corresponding published images, not the mutable `main` tip.

| Display name                             | Git tag             | Container tag      |
| ---------------------------------------- | ------------------- | ------------------ |
| Paperless-ngx 2.7.2 – Lavida Edition 1   | `v2.7.2-lavida.1`   | `2.7.2-lavida.1`   |
| Paperless-ngx 2.20.15 – Lavida Edition 1 | `v2.20.15-lavida.1` | `2.20.15-lavida.1` |
| Paperless-ngx 3.3.3 – Lavida Edition 1   | `v3.3.3-lavida.1`   | `3.3.3-lavida.1`   |

Images are in `ghcr.io/lavidade/paperless-ngx`. Package access requires permission.
`latest` selects the highest published stable Lavida version, currently 3.3.3.
Pin a version or digest for controlled upgrades. Publication is not deployment
approval. Consult the upstream migration guide: v3 requires the 2.20.15 bridge.

## Provenance and immutable releases

Release notes record the exact OCI index digest, immutable image revision and
Git source snapshot. Existing images are promoted by preserving manifest bytes;
no rebuild, relabel or modification of an existing stable tag is performed.
For historical images, source snapshots omit operational Markdown only; all
application, test and build files match the recorded OCI source revision.
The snapshot commit and complete tree therefore differ from that OCI revision.
Old candidate labels inside immutable images remain unchanged.

The maintained `main` source contains later fixes and is deliberately **not**
represented as the exact source of those previously tested immutable images.
Synthetic ASN checks do not establish full upgrade, OCR, UI or production
acceptance. See [Shared ASN](ASN-COMPATIBILITY.md).

## Future publication

Adopt upstream releases manually after choosing an official stable upstream tag;
there is no automatic upstream merge or prerelease adoption. Review changes,
run the test suites and build/test an explicit versioned image. Do not build or
publish floating branch tags. Create the stable Git source tag and publish a
GitHub release recording the approved image digest and expected OCI revision.
Then dispatch **Publish Lavida Edition** from `main` with that release tag,
digest and revision. The publishing environment can require maintainer approval.

The workflow validates the published non-prerelease, image revision, platform
manifests and blobs, refuses a mismatching existing stable tag, and promotes the
same manifest bytes. A serialized publication compares stable semantic versions
before updating `latest`; publishing an older release cannot downgrade it.
No branch push builds/publishes images. Obsolete inherited release, translation,
cleanup and candidate-publishing automations have been removed. Backend,
frontend, lint, static analysis, documentation and CodeQL checks remain.
