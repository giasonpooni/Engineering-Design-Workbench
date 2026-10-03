"""Transport digest-bound native Git objects; never execute imported source."""
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

BINDINGS = json.loads(r'''{
  "bundle_sha256": "e21e98d2e1a9ae6bb96ebdc765b872b748baf5cc9c3d29880163fdae371729c3",
  "bundle_size_bytes": 446851,
  "control_ref": "refs/heads/transport/net-scientific-web-demo-20261003",
  "destination_ref": "refs/heads/feat/net-scientific-web-demo-qualified-20261003",
  "fetch_prerequisite": "98b7dfccec61f295d0bd0240723fb64bf0f58d17",
  "fusion_ancestors": [
    "d30db0707407800675520e23b52e1fc1c8e02af9",
    "1824a35f20c0c897ed304f7ae7b8ae7e40e4d851",
    "4871b306ced4ae33866de75c809c61cea5cf485f"
  ],
  "head": "1b6c6577096de04181ab6ed3bafb6f9178f5ab53",
  "imports_manifest_blob": "d3c410a445e1377975cf078fe8aa83259b595fd2",
  "instruments_tree": "191dbe2c663d7b404e7c472435c512c639792413",
  "modules": [
    {
      "import_revision": "e41f61cf5909e58a1a2e60612308ccffe0bfe7de",
      "import_tree": "07d51585dee49b2d9ad2f3a4d9a01e708d1411cf",
      "path": "instruments/measurement/calibration",
      "role": "mcur"
    },
    {
      "import_revision": "13c5fe75c7e829c24bae12fcf8386d4831224d4e",
      "import_tree": "7d833657e7f838ac1b6ad6d0c3fb783151d1e85e",
      "path": "instruments/measurement/clocksync",
      "role": "tbrt"
    },
    {
      "import_revision": "9d22326c9e230f0d8d21b00ce210e10e72e968fd",
      "import_tree": "e3dc03481e2e380c7d9e4b978c3f9dc7f7359b52",
      "path": "instruments/mathematics/observability",
      "role": "oit"
    },
    {
      "import_revision": "4ec062bb72caa76ce1405f2851766589cee9d160",
      "import_tree": "33921b5f1ed0f5d03ba3fef6aa759becdde1e5ac",
      "path": "instruments/inference/state-inference",
      "role": "gsie"
    },
    {
      "import_revision": "fb01b4a702ba9314b211f933eda800a1e3e9efed",
      "import_tree": "f7582f6fd1b0c965ef7dc0690628f49d57a67e80",
      "path": "instruments/inference/state-recompiler",
      "role": "cbsr"
    },
    {
      "import_revision": "00a3f3537964374efbf72d82e4188db002457cd8",
      "import_tree": "de83e5df6448866a29e50f0e9d29cab019bba2d5",
      "path": "instruments/inference/faultsense",
      "role": "fdir"
    },
    {
      "import_revision": "928ae6a76d4f853aa8306fef8207f81244b7066f",
      "import_tree": "04d48ef9cf84a73a0cd029187263dca89d7c7e56",
      "path": "instruments/verification/estimator-bench",
      "role": "set"
    },
    {
      "import_revision": "01c84b6d2e60b58ad281735f5ff70eb5c6a3c87f",
      "import_tree": "7aea75468e6bee6d1421b300627c058305cb9c5d",
      "path": "instruments/mathematics/sensor-design",
      "role": "edspt"
    },
    {
      "import_revision": "bda30a8bd750c7034fa8db4760d74e35eacb8c66",
      "import_tree": "8c18ebad8a998991fce6d460492ba65731b3694e",
      "path": "instruments/mathematics/linear-dynamics",
      "role": "sidt"
    },
    {
      "import_revision": "341e3586075d6e901cb5528414ef685a58cf4def",
      "import_tree": "e1e72a0dbf0492c8cf7a03837a25f9ea83e02da8",
      "path": "instruments/mathematics/sensitivity",
      "role": "jspt"
    },
    {
      "import_revision": "a67cfef9f132d2a756186f34dcc718404084126e",
      "import_tree": "ea6f143188dd81aa8bff36973eb94d6e3693c7a2",
      "path": "instruments/measurement/metrology",
      "role": "rci"
    },
    {
      "import_revision": "749eb75e7300597da54f3e5ab8cfdc7d05e64878",
      "import_tree": "eaa9f5f5be58b0cbac95002f6bdd0e826428fb44",
      "path": "instruments/measurement/signal-processing",
      "role": "stfe"
    },
    {
      "import_revision": "fb30ddf35d860835a2b0a633f735e922d86ea808",
      "import_tree": "2ce81327e6cd7beefd89c60d68d9bbf9b1cfba51",
      "path": "instruments/mathematics/polygon-trajectories",
      "role": "tsde"
    },
    {
      "import_revision": "1f7bbe380651e8df82db1760d880330aee3dc229",
      "import_tree": "b715b302e698a4ae07a48de0a144f0aa73aa0639",
      "path": "instruments/mathematics/surface",
      "role": "csg"
    },
    {
      "import_revision": "4dc4da256873b03d82b3355af65638254ad15b53",
      "import_tree": "906aec5440d412490550b8c16e7260591a1a4a57",
      "path": "instruments/composition/retrieval-agent",
      "role": "sra"
    },
    {
      "import_revision": "8ae062b3578b02516a34fcd55d62d68187b57caa",
      "import_tree": "db5eebf6edd6909e50f4e106c955d2796966b384",
      "path": "instruments/resources/yield-weighted",
      "role": "ywir"
    },
    {
      "import_revision": "1411f8dcc2d14a33fab4f58ca85d1f5089894ff4",
      "import_tree": "641c48a94afb171119fa1fbd02b5415805a1dd75",
      "path": "instruments/domain/bim-estimator",
      "role": "cse"
    },
    {
      "import_revision": "6f1b339dfa103bc45b40f34170043bc23a010c57",
      "import_tree": "896ef8521dfb26a288b10e00ca46d606e77f6723",
      "path": "instruments/views/real-time-globe",
      "role": "gsv"
    },
    {
      "import_revision": "b788489373cbbeebf69667ddf06c048855e22836",
      "import_tree": "4facb96d2727d7e250790456e31bb07dc7b55703",
      "path": "instruments/representation/frame-mapper",
      "role": "framemapper"
    },
    {
      "import_revision": "da2dc23857dd8665473d3b8d32e6b7452866e749",
      "import_tree": "00f19f7ee02d9e65735b5071382d8fb21a727e25",
      "path": "instruments/execution/compute-runtime",
      "role": "scr"
    },
    {
      "import_revision": "3144e3e694419b0c8579938e8d28523174e36abd",
      "import_tree": "5a76aefab8974d46e4e8eac79371c553461bf491",
      "path": "instruments/domain/flowstate",
      "role": "fsrt"
    }
  ],
  "original_ref": "refs/heads/feat/net-scientific-web-demo-qualified-20261003",
  "prerequisites": [
    "6989ffd2fd97d54367d17a20fd51e9945d7ed18e",
    "d49e6215db7bbce86b0ea0896afc679f0ed7b728",
    "98b7dfccec61f295d0bd0240723fb64bf0f58d17"
  ],
  "repository": "atomtrapping/Notations-Systems-Terminal",
  "repository_id": 1377790873,
  "reviewed_workflows": [
    {
      "bytes": 2736,
      "git_blob_sha": "8536cfe582554c396bbef76dc01656eac7e599f3",
      "path": ".github/workflows/hypergraph-rewrite.yml",
      "permissions": {
        "contents": "read"
      },
      "runs_on_control_branch_push": false,
      "sha256": "67ac6caf0d1c10d7fdf8200778bc2f5b977d65fce7af182b4d0db8d2e8f71755",
      "triggers": [
        "pull_request",
        "workflow_dispatch"
      ]
    },
    {
      "bytes": 4191,
      "git_blob_sha": "58288c23db8e8e737d61a6fc7cf1a8fbfae7f6a3",
      "path": ".github/workflows/operator-readiness.yml",
      "permissions": {
        "contents": "read"
      },
      "runs_on_control_branch_push": false,
      "sha256": "44754a79a5213e4579131ac061f6d087560a0fe649fe22f5955968e24b6366ed",
      "triggers": [
        "pull_request",
        "push",
        "workflow_dispatch"
      ]
    },
    {
      "bytes": 1868,
      "git_blob_sha": "32d274b840a9cf02c0dc0323b1f2e379b0e10844",
      "path": ".github/workflows/scientific-web-demo.yml",
      "permissions": {
        "contents": "read"
      },
      "runs_on_control_branch_push": false,
      "sha256": "4412558e5acea6c24b374a2f0e58c01b84897ac8232e4ccabfe275683fa2fd94",
      "triggers": [
        "pull_request",
        "push",
        "workflow_dispatch"
      ]
    }
  ],
  "schema": "notations.net-web-demo-native-transport.v1",
  "source_roots": [
    "00a3f3537964374efbf72d82e4188db002457cd8",
    "01c84b6d2e60b58ad281735f5ff70eb5c6a3c87f",
    "06c47bd851d8ea8b363a6bbe60a96c7448cbe12e",
    "13c5fe75c7e829c24bae12fcf8386d4831224d4e",
    "1411f8dcc2d14a33fab4f58ca85d1f5089894ff4",
    "1f7bbe380651e8df82db1760d880330aee3dc229",
    "3144e3e694419b0c8579938e8d28523174e36abd",
    "341e3586075d6e901cb5528414ef685a58cf4def",
    "4dc4da256873b03d82b3355af65638254ad15b53",
    "4ec062bb72caa76ce1405f2851766589cee9d160",
    "6f1b339dfa103bc45b40f34170043bc23a010c57",
    "749eb75e7300597da54f3e5ab8cfdc7d05e64878",
    "8ae062b3578b02516a34fcd55d62d68187b57caa",
    "928ae6a76d4f853aa8306fef8207f81244b7066f",
    "98ab2f312cb7f9f4dbb18b25f762593eba56653e",
    "9d22326c9e230f0d8d21b00ce210e10e72e968fd",
    "a67cfef9f132d2a756186f34dcc718404084126e",
    "b788489373cbbeebf69667ddf06c048855e22836",
    "bda30a8bd750c7034fa8db4760d74e35eacb8c66",
    "bdfcb041836e86ab1ce93688b127f8960e8d08cf",
    "da2dc23857dd8665473d3b8d32e6b7452866e749",
    "e13e46facc125682776f165ce1b0460b4ff9410a",
    "e41f61cf5909e58a1a2e60612308ccffe0bfe7de",
    "e8f0938ab243a1905792ba2c43439cb4f40cd4be",
    "f863bdd69d49224e0cdc871943bbb052e5b0a975",
    "fb01b4a702ba9314b211f933eda800a1e3e9efed",
    "fb30ddf35d860835a2b0a633f735e922d86ea808"
  ],
  "tree": "2d78d64975760d67ebdf23aea0a25e4d60a3d448"
}''')
MANIFEST_SHA256 = "fc794aaf8304bc326306f91bd13ff0ce90f67915b147b96e39c3637d23d6bc53"
ROOT = Path(__file__).resolve().parent
REPOSITORY = "atomtrapping/Notations-Systems-Terminal"
REPOSITORY_ID = 1377790873
URL = "https://github.com/" + REPOSITORY + ".git"
MAX_BUNDLE_BYTES = 10 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def clean_environment():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in {
               "GH_TOKEN", "GITHUB_TOKEN", "NET_NATIVE_PUSH_TOKEN"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return env


def git(bare, *args, env=None, timeout=180):
    command = ["git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
               "-c", "core.fsmonitor=false", "-c", "gc.auto=0",
               "-c", "credential.helper=", "-c", "http.extraHeader=",
               "-c", "http.followRedirects=false",
               "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never"]
    if bare is not None:
        command += ["--git-dir=" + str(bare)]
    result = subprocess.run(command + list(args), check=True, capture_output=True,
                            text=True, timeout=timeout, env=env or clean_environment())
    return result.stdout.strip()


def payload():
    manifest_path = ROOT / "prerequisites.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "Manifest is not a regular file")
    require(manifest_path.stat().st_size <= 64 * 1024, "Manifest size exceeds bound")
    data = manifest_path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == MANIFEST_SHA256, "Manifest digest mismatch")
    manifest = json.loads(data)
    require(manifest == BINDINGS, "Fixed publication bindings changed")
    require(manifest["repository"] == REPOSITORY and manifest["repository_id"] == REPOSITORY_ID,
            "Repository identity changed")
    bundle = ROOT / "native-history.bundle"
    require(bundle.is_file() and not bundle.is_symlink(), "Bundle is not a regular file")
    require(bundle.stat().st_size == manifest["bundle_size_bytes"] <= MAX_BUNDLE_BYTES,
            "Unexpected or oversized bundle")
    require(hashlib.sha256(bundle.read_bytes()).hexdigest() == manifest["bundle_sha256"],
            "Bundle digest mismatch")
    prerequisites, refs = [], []
    with bundle.open("rb") as stream:
        require(stream.readline(128) == b"# v2 git bundle\n", "Expected SHA-1 bundle version 2")
        for _ in range(len(manifest["prerequisites"]) + 2):
            line = stream.readline(4096)
            require(line and len(line) < 4096, "Invalid or excessive bundle header")
            if line == b"\n":
                break
            if line.startswith(b"-"):
                prerequisites.append(line[1:].split(b" ", 1)[0].decode("ascii"))
            else:
                refs.append(line.rstrip().decode("ascii"))
        else:
            raise RuntimeError("Bundle header exceeds fixed one-ref scope")
        require(stream.read(4) == b"PACK", "Missing native Git pack")
    require(prerequisites == manifest["prerequisites"] and 1 <= len(prerequisites) <= 16,
            "Expected exact fixed bundle boundary prerequisites")
    require(refs == [manifest["head"] + " " + manifest["original_ref"]],
            "Unexpected advertised bundle ref")
    require(manifest["original_ref"] == manifest["destination_ref"],
            "Original feature branch identity changed")
    require(len(manifest["modules"]) == 21 and len(manifest["source_roots"]) == 27,
            "Imported source scope changed")
    return manifest, bundle


def runtime_repository():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected repository")
    require(os.environ.get("GITHUB_REPOSITORY_ID") == str(REPOSITORY_ID), "Unexpected repository ID")
    require(os.environ.get("GITHUB_REF") == BINDINGS["control_ref"], "Unexpected control branch")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "Only the reviewed push event is allowed")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[0-9]+", os.environ.get(key, "")) is not None, "Invalid run identity")
    require(re.fullmatch(r"[0-9a-f]{40}", os.environ.get("GITHUB_SHA", "")) is not None,
            "Invalid control commit")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    return temp / ("net-web-demo-native-" + os.environ["GITHUB_RUN_ID"] + "-" +
                   os.environ["GITHUB_RUN_ATTEMPT"] + ".git")


def check_public_repository():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY,
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "notations-net-demo-native-transport"})
    with opener.open(request, timeout=30) as response:
        require(response.geturl() == request.full_url, "Public repository redirected")
        data = response.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, "Repository metadata exceeds bound")
    metadata = json.loads(data)
    require(metadata.get("id") == REPOSITORY_ID and metadata.get("private") is False
            and metadata.get("full_name") == REPOSITORY, "Public repository identity changed")


def check_native_objects(bare, manifest):
    head = manifest["head"]
    prerequisite = manifest["fetch_prerequisite"]
    require(git(bare, "rev-parse", "--show-object-format") == "sha1", "Unexpected Git object format")
    require(git(bare, "rev-parse", "refs/heads/imported") == head, "Original commit changed")
    require(git(bare, "rev-parse", head + "^{tree}") == manifest["tree"], "Qualified tree changed")
    git(bare, "fsck", "--full", "--strict", "--no-reflogs", timeout=300)
    git(bare, "merge-base", "--is-ancestor", prerequisite, head)
    for revision in manifest["prerequisites"]:
        git(bare, "merge-base", "--is-ancestor", revision, prerequisite)
    for revision in manifest["fusion_ancestors"]:
        git(bare, "merge-base", "--is-ancestor", revision, head)
    # Each public instrument history is reachable through the fixed published main.
    for revision in manifest["source_roots"]:
        git(bare, "merge-base", "--is-ancestor", revision, prerequisite)
        git(bare, "merge-base", "--is-ancestor", revision, head)
    for revision in (prerequisite, head):
        require(git(bare, "rev-parse", revision + ":instruments") == manifest["instruments_tree"],
                "Imported instrument subtree changed")
        require(git(bare, "rev-parse", revision + ":instruments/manifest.json") == manifest["imports_manifest_blob"],
                "Imported instrument manifest changed")
    for module in manifest["modules"]:
        require(git(bare, "rev-parse", module["import_revision"] + "^{tree}") == module["import_tree"],
                "Original source tree changed: " + module["role"])
        for revision in (prerequisite, head):
            require(git(bare, "rev-parse", revision + ":" + module["path"]) == module["import_tree"],
                    "Imported module tree changed: " + module["role"])
    for workflow in manifest["reviewed_workflows"]:
        require(git(bare, "rev-parse", head + ":" + workflow["path"]) == workflow["git_blob_sha"],
                "Reviewed feature workflow bytes changed")


def prepare(bare, manifest, bundle):
    require(not bare.exists(), "Import workspace already exists")
    check_public_repository()
    git(None, "init", "--bare", "--object-format=sha1", str(bare))
    prerequisite = manifest["fetch_prerequisite"]
    git(bare, "fetch", "--no-tags", "--no-write-fetch-head", URL, prerequisite, timeout=360)
    git(bare, "cat-file", "-e", prerequisite + "^{commit}")
    git(bare, "update-ref", "refs/prerequisites/" + prerequisite, prerequisite)
    git(bare, "bundle", "verify", str(bundle))
    git(bare, "bundle", "unbundle", str(bundle))
    git(bare, "update-ref", "refs/heads/imported", manifest["head"])
    check_native_objects(bare, manifest)
    print(json.dumps({"status": "verified native objects", "head": manifest["head"],
                      "tree": manifest["tree"], "bundle_sha256": manifest["bundle_sha256"],
                      "control_sha": os.environ["GITHUB_SHA"],
                      "destination": manifest["destination_ref"]}, sort_keys=True))


def publish(bare, manifest):
    require(bare.is_dir(), "Verified native objects are missing")
    check_native_objects(bare, manifest)
    head, destination = manifest["head"], manifest["destination_ref"]
    existing = git(None, "ls-remote", "--heads", URL, destination)
    if existing:
        require(existing.split() == [head, destination], "Destination branch already has another head")
        print("Original native head is already published; no ref update performed.")
        return
    token = os.environ.get("NET_NATIVE_PUSH_TOKEN", "")
    require(bool(token), "Repository push token is unavailable")
    askpass = bare.parent / (bare.name + ".askpass.py")
    require(not askpass.exists(), "Credential helper already exists")
    askpass.write_text("#!/usr/bin/python3 -I\nimport os, sys\n"
                       "if 'username' in sys.argv[1].lower():\n"
                       "    print('x-access-token')\n"
                       "elif 'password' in sys.argv[1].lower():\n"
                       "    print(os.environ['NET_NATIVE_PUSH_TOKEN'])\n"
                       "else:\n    raise SystemExit(1)\n", encoding="utf-8")
    askpass.chmod(0o700)
    env = clean_environment()
    env.update(GIT_ASKPASS=str(askpass), NET_NATIVE_PUSH_TOKEN=token)
    try:
        result = git(bare, "push", "--porcelain", URL, head + ":" + destination,
                     env=env, timeout=300)
        print(result)
    finally:
        askpass.unlink(missing_ok=True)
    require(git(None, "ls-remote", "--heads", URL, destination).split() == [head, destination],
            "Published ref did not match the original native commit")
    print(json.dumps({"status": "published native review branch", "head": head,
                      "tree": manifest["tree"], "destination": destination}, sort_keys=True))


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
        # Only fixed public URLs and object/ref IDs appear in command strings.
        # Process environments, helper output, and credentials are never printed.
        print("Native demo import blocked: " + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-4000:].strip(), file=sys.stderr)
        raise SystemExit(1) from None
