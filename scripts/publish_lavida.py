# ruff: noqa: INP001
"""Promote an explicitly selected tested GHCR index; never rebuild stable tags."""

import base64
import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request

PACKAGE = "lavidade/paperless-ngx"
PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)-lavida\.(\d+)\Z")
ACCEPT = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"


def version(tag):
    match = PATTERN.fullmatch(tag)
    if not match:
        raise ValueError("Only stable X.Y.Z-lavida.N releases are accepted")
    return tuple(map(int, match.groups()))


def request(url, token, method="GET", data=None, content_type=None):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json"
        if url.startswith("https://api.github.com/")
        else ACCEPT,
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read(), response.headers


def main():
    tag = os.environ["RELEASE_TAG"]
    target_version = version(tag)
    if not tag.startswith("v"):
        raise ValueError("GitHub release tag must start with v")
    digest = os.environ["IMAGE_DIGEST"]
    revision = os.environ["OCI_REVISION"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid digest")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid revision")
    credential = os.environ["GH_TOKEN"]
    data, _ = request(
        "https://api.github.com/repos/" + PACKAGE + "/releases/tags/" + tag,
        credential,
    )
    release = json.loads(data)
    if release["draft"] or release["prerelease"] or release["tag_name"] != tag:
        raise ValueError("A published stable release is required")
    # Explicit expected digest and source revision must be reviewed in release notes.
    if digest not in release["body"] or revision not in release["body"]:
        raise ValueError(
            "Release notes must record the approved digest and OCI revision",
        )
    basic = base64.b64encode(
        (os.environ.get("GITHUB_ACTOR", "hugchristian") + ":" + credential).encode(),
    ).decode()
    req = urllib.request.Request(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:"
        + PACKAGE
        + ":pull,push",
        headers={"Authorization": "Basic " + basic},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        token = json.load(response)["token"]
    base = "https://ghcr.io/v2/" + PACKAGE
    raw, headers = request(base + "/manifests/" + digest, token)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Manifest digest mismatch")
    index = json.loads(raw)
    children = index.get("manifests")
    if not children:
        raise ValueError("Expected a platform index")
    revisions = set()
    for child in children:
        manifest_raw, _ = request(base + "/manifests/" + child["digest"], token)
        manifest = json.loads(manifest_raw)
        config_raw, _ = request(base + "/blobs/" + manifest["config"]["digest"], token)
        config = json.loads(config_raw)
        if child.get("platform", {}).get("os") != "unknown":
            revisions.add(
                config.get("config", {})
                .get("Labels", {})
                .get("org.opencontainers.image.revision"),
            )
        for blob in manifest.get("layers", []):
            request(base + "/blobs/" + blob["digest"], token, method="HEAD")
    if revisions != {revision}:
        raise ValueError("OCI source revision mismatch")

    def existing(name):
        try:
            body, _ = request(base + "/manifests/" + name, token)
            return "sha256:" + hashlib.sha256(body).hexdigest()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def alias(name, immutable):
        old = existing(name)
        if immutable and old is not None and old != digest:
            raise ValueError("Refusing to overwrite stable tag " + name)
        if old != digest:
            request(
                base + "/manifests/" + name,
                token,
                method="PUT",
                data=raw,
                content_type=headers["Content-Type"],
            )
        if existing(name) != digest:
            raise ValueError("Alias verification failed")

    alias(tag[1:], immutable=True)
    # Enumerate all registry tags, including pagination, to prevent late releases
    # from downgrading latest. No floating branch tags are ever published.
    url = base + "/tags/list?n=100"
    stable = []
    while url:
        body, page_headers = request(url, token)
        stable.extend(
            version(t) for t in json.loads(body).get("tags", []) if PATTERN.fullmatch(t)
        )
        link = page_headers.get("Link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = urllib.request.urljoin(url, match.group(1)) if match else None
    if target_version >= max(stable, default=target_version):
        alias("latest", immutable=False)
    logging.warning("Verified stable publication: %s %s", tag, digest)


if __name__ == "__main__":
    main()
