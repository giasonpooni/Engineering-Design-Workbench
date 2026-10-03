from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.artifact_provenance import (
    boundary_review,
    declaration_from_spec,
    inspect_declaration,
    validate_declaration,
)


def ref(char):
    return "sha256:" + char * 64


def spec(*, owner="Notation Systems", asset_class="OPEN_INFRASTRUCTURE",
         artifact_id="net:semantic-plane", artifact_ref=None,
         license_expression="MPL-2.0", dependencies=None):
    return {
        "declared_at": "2026-09-29T18:00:00-04:00",
        "artifact": {
            "artifact_id": artifact_id,
            "kind": "source-code",
            "content_ref": artifact_ref or ref("1"),
        },
        "ownership": {
            "declared_owner": owner,
            "asset_class": asset_class,
            "basis_refs": ["repository:owner-declaration"],
        },
        "repository": {
            "url": "https://github.com/example/repository",
            "revision": "a" * 40,
            "path": "src/example.py",
        },
        "origin": {
            "kind": "ORIGINAL",
            "description": "Original repository work.",
            "source_refs": ["repository:commit:" + "a" * 40],
        },
        "license": {
            "expression": license_expression,
            "license_text_ref": ref("b"),
            "notice_refs": ["repository:LICENSE"],
        },
        "contributors": [{
            "id": "contributor:giason",
            "role": "author",
            "contribution_refs": ["repository:commit:" + "a" * 40],
        }],
        "dependencies": dependencies or [],
        "use_policy": {
            "policy_id": "policy:open-infrastructure",
            "declared_allowed_contexts": ["research", "education", "commercial-use-subject-to-license"],
            "declared_prohibited_contexts": [],
            "basis_refs": ["repository:LICENSE"],
        },
    }


def test_open_infrastructure_declaration_is_descriptive_not_rights_authority():
    value = declaration_from_spec(spec())
    validate_declaration(value)
    inspected = inspect_declaration(value)
    assert inspected["asset_class"] == "OPEN_INFRASTRUCTURE"
    assert inspected["declared_owner"] == "Notation Systems"
    assert inspected["rights_adjudicated"] is False
    assert inspected["license_compatibility_verified"] is False
    assert inspected["execution_authority"] is False


def test_cartesian_proprietary_asset_remains_distinct_from_open_tooling():
    value = declaration_from_spec(spec(
        owner="Cartesian Graphics",
        asset_class="PROPRIETARY_IP",
        artifact_id="1792:asset:smith-hammer",
        artifact_ref=ref("c"),
        license_expression="LicenseRef-Cartesian-Proprietary",
    ))
    assert value["ownership"]["declared_owner"] == "Cartesian Graphics"
    assert value["ownership"]["asset_class"] == "PROPRIETARY_IP"
    assert value["license"]["expression"] == "LicenseRef-Cartesian-Proprietary"


def test_declared_use_policy_cannot_contradict_itself():
    value = spec()
    value["use_policy"]["declared_prohibited_contexts"] = ["research"]
    with pytest.raises(ValueError, match="both allowed and prohibited"):
        declaration_from_spec(value)


def test_tamper_breaks_declaration_identity():
    value = declaration_from_spec(spec())
    value["ownership"]["declared_owner"] = "Someone Else"
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_declaration(value)


def test_open_infrastructure_depending_on_proprietary_ip_is_flagged_for_review():
    cartesian = declaration_from_spec(spec(
        owner="Cartesian Graphics",
        asset_class="PROPRIETARY_IP",
        artifact_id="1792:asset:terrain",
        artifact_ref=ref("d"),
        license_expression="LicenseRef-Cartesian-Proprietary",
    ))
    parent_spec = spec(dependencies=[{
        "artifact_id": "1792:asset:terrain",
        "relationship": "INCORPORATES",
        "content_ref": ref("d"),
        "license_expression": "LicenseRef-Cartesian-Proprietary",
        "source_ref": "repository:cartesian:terrain",
    }])
    parent = declaration_from_spec(parent_spec)
    report = boundary_review(parent, [cartesian])
    assert report["findings"][0]["status"] == "REVIEW_REQUIRED"
    assert report["claims"]["rights_adjudicated"] is False


def test_proprietary_product_using_open_tooling_is_not_automatically_flagged_as_bad():
    open_tool = declaration_from_spec(spec())
    parent = declaration_from_spec(spec(
        owner="Cartesian Graphics",
        asset_class="PROPRIETARY_IP",
        artifact_id="1792:production-recipe",
        artifact_ref=ref("e"),
        license_expression="LicenseRef-Cartesian-Proprietary",
        dependencies=[{
            "artifact_id": "net:semantic-plane",
            "relationship": "GENERATED_WITH",
            "content_ref": ref("1"),
            "license_expression": "MPL-2.0",
            "source_ref": "repository:notations:net",
        }],
    ))
    report = boundary_review(parent, [open_tool])
    assert report["findings"][0]["status"] == "CROSS_OWNER"
    assert report["findings"][0]["status"] != "REVIEW_REQUIRED"


@pytest.mark.parametrize("fault", ["owner_class", "revision", "license", "relationship", "absolute_path"])
def test_malformed_provenance_refuses(fault):
    value = spec()
    if fault == "owner_class":
        value["ownership"]["asset_class"] = "MAGIC"
    elif fault == "revision":
        value["repository"]["revision"] = "main"
    elif fault == "license":
        value["license"]["expression"] = "<script>"
    elif fault == "relationship":
        value["dependencies"] = [{
            "artifact_id": "x",
            "relationship": "COPIED",
            "content_ref": ref("f"),
            "license_expression": "MPL-2.0",
            "source_ref": "x",
        }]
    else:
        value["repository"]["path"] = "/absolute/path"
    with pytest.raises(ValueError):
        declaration_from_spec(value)


def test_cli_create_and_inspect_outside_business_logic(tmp_path):
    spec_path = tmp_path / "spec.json"
    out = tmp_path / "provenance.json"
    spec_path.write_text(json.dumps(spec()))
    subprocess.run([
        sys.executable, "-m", "ciw.net", "provenance", "create",
        str(spec_path), "--output", str(out),
    ], cwd=tmp_path, check=True)
    inspected = json.loads(subprocess.check_output([
        sys.executable, "-m", "ciw.net", "provenance", "inspect", str(out),
    ], cwd=tmp_path, text=True))
    assert inspected["declared_owner"] == "Notation Systems"
    assert inspected["rights_adjudicated"] is False
