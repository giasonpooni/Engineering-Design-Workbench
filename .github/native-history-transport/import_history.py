"""Transport reviewed native Git objects; never execute the imported source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

REPOSITORY = "atomtrapping/Notations-Systems-Terminal"
REPOSITORY_ID = 1377790873
CONTROL_REF = "refs/heads/transport/native-superrepo-20261003"
DESTINATION_REF = "refs/heads/import/native-superrepo-6989ffd2-20261003"
ORIGINAL_REF = "refs/heads/feat/engineering-superrepo-20261003"
HEAD = "6989ffd2fd97d54367d17a20fd51e9945d7ed18e"
TREE = "5584b8c3e810c4200285144975671338d1970860"
MANIFEST_SHA256 = "dc577a77a8cee7c9154db90e4147242e9f602c63886de8dddf347e137a4b872b"
BUNDLE_SHA256 = "1162889ca7f6b7380b11c0eb8d578956c1f9f9b1928b5c5aa3e4637b5cc4b626"
ROOT = Path(__file__).resolve().parent
URL = "https://github.com/" + REPOSITORY + ".git"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def clean_environment():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k not in {"GH_TOKEN", "GITHUB_TOKEN", "NET_NATIVE_PUSH_TOKEN"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return env


def git(bare, *args, env=None, timeout=180):
    command = ["git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
               "-c", "core.fsmonitor=false", "-c", "gc.auto=0",
               "-c", "credential.helper=", "-c", "http.extraHeader=",
               "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never"]
    if bare is not None:
        command += ["--git-dir=" + str(bare)]
    result = subprocess.run(command + list(args), check=True, capture_output=True,
                            text=True, timeout=timeout, env=env or clean_environment())
    return result.stdout.strip()


def payload():
    data = (ROOT / "prerequisites.json").read_bytes()
    require(hashlib.sha256(data).hexdigest() == MANIFEST_SHA256, "Manifest digest mismatch")
    manifest = json.loads(data)
    for key, expected in {"repository": REPOSITORY, "repository_id": REPOSITORY_ID,
                          "control_ref": CONTROL_REF, "destination_ref": DESTINATION_REF,
                          "original_ref": ORIGINAL_REF, "head": HEAD, "tree": TREE,
                          "bundle_sha256": BUNDLE_SHA256}.items():
        require(manifest[key] == expected, "Fixed manifest binding changed: " + key)
    bundle = ROOT / "native-history.bundle"
    require(bundle.stat().st_size == 159203, "Unexpected bundle size")
    require(hashlib.sha256(bundle.read_bytes()).hexdigest() == BUNDLE_SHA256, "Bundle digest mismatch")
    prerequisites, refs = [], []
    with bundle.open("rb") as stream:
        require(stream.readline() == b"# v2 git bundle\n", "Expected SHA-1 bundle version 2")
        for line in iter(stream.readline, b""):
            if line == b"\n":
                break
            if line.startswith(b"-"):
                prerequisites.append(line[1:].split(b" ", 1)[0].decode("ascii"))
            else:
                refs.append(line.rstrip().decode("ascii"))
        require(stream.read(4) == b"PACK", "Missing native Git pack")
    require(refs == [HEAD + " " + ORIGINAL_REF], "Unexpected advertised bundle ref")
    require(len(prerequisites) == len(set(prerequisites)) == 26, "Unexpected prerequisite count")
    require(set(prerequisites) == {x["revision"] for x in manifest["prerequisites"]},
            "Bundle prerequisite list changed")
    require(len(manifest["source_roots"]) == 27 and len(manifest["modules"]) == 21,
            "Public source scope changed")
    return manifest, bundle


def runtime_repository():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected repository")
    require(os.environ.get("GITHUB_REF") == CONTROL_REF, "Unexpected control branch")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "Only the reviewed push event is allowed")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[0-9]+", os.environ.get(key, "")) is not None, "Invalid run identity")
    sha = os.environ.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "Invalid control commit")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    return temp / ("native-superrepo-" + os.environ["GITHUB_RUN_ID"] + "-" +
                   os.environ["GITHUB_RUN_ATTEMPT"] + ".git")


def check_public_repositories(manifest):
    repositories = {REPOSITORY: REPOSITORY_ID}
    for row in manifest["prerequisites"] + manifest["source_roots"]:
        require(re.fullmatch(r"atomtrapping/[A-Za-z0-9_.-]+", row["repository"]) is not None,
                "Unexpected source URL")
        require(re.fullmatch(r"[0-9a-f]{40}", row["revision"]) is not None,
                "Incomplete source revision")
        existing = repositories.setdefault(row["repository"], row["repository_id"])
        require(existing == row["repository_id"], "Source repository identity collision")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for repository, expected_id in sorted(repositories.items()):
        request = urllib.request.Request("https://api.github.com/repos/" + repository,
                                         headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": "notations-native-history-transport"})
        with opener.open(request, timeout=30) as response:
            require(response.geturl() == request.full_url, "Source repository redirected")
            metadata = json.load(response)
        require(metadata.get("id") == expected_id and metadata.get("private") is False
                and metadata.get("full_name") == repository, "Public repository identity changed")


def check_native_objects(bare, manifest):
    require(git(bare, "rev-parse", "--show-object-format") == "sha1", "Unexpected Git object format")
    require(git(bare, "rev-parse", "refs/heads/imported") == HEAD, "Original commit changed")
    require(git(bare, "rev-parse", HEAD + "^{tree}") == TREE, "Qualified tree changed")
    git(bare, "fsck", "--full", "--strict", "--no-reflogs", timeout=300)
    for row in manifest["source_roots"]:
        git(bare, "merge-base", "--is-ancestor", row["revision"], HEAD)
    for module in manifest["modules"]:
        require(git(bare, "rev-parse", module["import_revision"] + "^{tree}") == module["import_tree"],
                "Original public source tree changed: " + module["role"])
        require(git(bare, "rev-parse", HEAD + ":" + module["path"]) == module["import_tree"],
                "Imported module tree changed: " + module["role"])


def prepare(bare, manifest, bundle):
    require(not bare.exists(), "Import workspace already exists")
    check_public_repositories(manifest)
    git(None, "init", "--bare", "--object-format=sha1", str(bare))
    for row in manifest["prerequisites"]:
        source = "https://github.com/" + row["repository"] + ".git"
        git(bare, "fetch", "--no-tags", "--no-write-fetch-head", source, row["revision"])
        git(bare, "cat-file", "-e", row["revision"] + "^{commit}")
        git(bare, "update-ref", "refs/prerequisites/" + row["revision"], row["revision"])
    git(bare, "bundle", "verify", str(bundle))
    git(bare, "bundle", "unbundle", str(bundle))
    git(bare, "update-ref", "refs/heads/imported", HEAD)
    check_native_objects(bare, manifest)
    print(json.dumps({"status": "verified native objects", "head": HEAD, "tree": TREE,
                      "bundle_sha256": BUNDLE_SHA256, "control_sha": os.environ["GITHUB_SHA"],
                      "destination": DESTINATION_REF}, sort_keys=True))


def publish(bare, manifest):
    require(bare.is_dir(), "Verified native objects are missing")
    check_native_objects(bare, manifest)
    existing = git(None, "ls-remote", "--heads", URL, DESTINATION_REF)
    if existing:
        require(existing.split() == [HEAD, DESTINATION_REF], "Destination branch already has another head")
        print("Original native head is already published; no ref update performed.")
        return
    token = os.environ.get("NET_NATIVE_PUSH_TOKEN", "")
    require(bool(token), "Repository push token is unavailable")
    askpass = bare.parent / (bare.name + ".askpass.py")
    require(not askpass.exists(), "Credential helper already exists")
    askpass.write_text("#!/usr/bin/env python3\nimport os, sys\n"
                       "if 'username' in sys.argv[1].lower():\n"
                       "    print('x-access-token')\n"
                       "elif 'password' in sys.argv[1].lower():\n"
                       "    print(os.environ['NET_NATIVE_PUSH_TOKEN'])\n"
                       "else:\n    raise SystemExit(1)\n")
    askpass.chmod(0o700)
    env = clean_environment()
    env.update(GIT_ASKPASS=str(askpass), NET_NATIVE_PUSH_TOKEN=token)
    try:
        result = git(bare, "push", "--porcelain", URL, HEAD + ":" + DESTINATION_REF,
                     env=env, timeout=300)
        print(result)
    finally:
        askpass.unlink(missing_ok=True)
    require(git(None, "ls-remote", "--heads", URL, DESTINATION_REF).split() == [HEAD, DESTINATION_REF],
            "Published ref did not match the original native commit")
    print(json.dumps({"status": "published native review branch", "head": HEAD, "tree": TREE,
                      "destination": DESTINATION_REF}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "publish"))
    args = parser.parse_args()
    manifest, bundle = payload()
    bare = runtime_repository()
    if args.mode == "prepare":
        prepare(bare, manifest, bundle)
    else:
        publish(bare, manifest)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Command strings contain only fixed public URLs and object/ref IDs.
        # Never print process environments or credential helper output.
        print("Native import blocked: " + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-4000:].strip(), file=sys.stderr)
        raise SystemExit(1) from None
