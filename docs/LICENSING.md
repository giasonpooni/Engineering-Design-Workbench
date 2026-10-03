# Platform licensing policy

PDT's first-party application code is licensed under
**GNU Affero General Public License version 3 or, at your option, any later
version (`AGPL-3.0-or-later`)**, except where an explicit component or file
notice states otherwise. The full license text is in [LICENSE](../LICENSE).
This is the platform policy for orchestration, investigation services and
first-party shared clients; it does not relicense upstream software.

This revision deliberately changes the previous `AGPL-3.0-only` declaration
for PDT first-party code. Earlier releases retain their recorded notices.
Copyright and separately licensed component notices remain intact. A future
change to another repository's license requires its own rights and dependency
review; membership in the Notation Systems stack is not a license grant.

## Component boundaries

| Component | License boundary |
| --- | --- |
| PDT application and first-party network services | `AGPL-3.0-or-later`, subject to explicit component exceptions and the rights of contributors. |
| PDT Godot client | First-party client code follows the PDT grant. The Godot engine remains MIT, with its own third-party notices. |
| Future PDT Bevy runtime | First-party application code follows the PDT grant. Bevy's usual MIT OR Apache-2.0 choice and per-file exceptions remain upstream terms. No Bevy integration is established by this policy. |
| Blender and a future `bpy` integration | Preserve Blender's GPL-family terms. Select and document a compatible license for the actual add-on and combined distribution before release; do not silently substitute the PDT default. |
| Scientific providers, drivers and other repositories | Retain their respective licenses and contribution notices. A shared API, pin or repository owner does not change those terms. |
| Assets, models, datasets and outputs | Retain their own provenance and rights. Running a tool does not automatically place input data or generated artifacts under PDT's software license. |

[Godot's licensing guide](https://docs.godotengine.org/en/stable/about/complying_with_licenses.html)
identifies its MIT license and additional third-party and asset notices.
[Bevy's license declaration](https://github.com/bevyengine/bevy#license)
describes its dual license and component/asset exceptions. Distribution records
must use the licenses of the actual pinned versions, not this summary alone.

[Blender's license page](https://www.blender.org/about/license/) describes
GPL-family distribution and Python add-on requirements. GPLv3 and AGPLv3 contain
specific combination provisions; they do not erase each component's original
license. The actual linking, copying and distribution determine the applicable
obligations. A separate process or file exchange is an architectural boundary,
not an automatic compatibility ruling.

For a Blender add-on, retain an explicit package/file notice, the Blender version
and dependencies, and the selected compatibility basis. Keep reusable PDT service
code separate from add-on implementation unless the combined work has been
reviewed. No add-on exception or automatic relicensing is created here.

## Distribution and network source

For each release or hosted deployment, retain the first-party revision,
dependency versions, original copyright/license notices, applicable NOTICE
files and the source/build materials required by the chosen licenses. Include
engine dependency and asset notices when those components are redistributed.

[AGPLv3 section 13](https://www.gnu.org/licenses/agpl-3.0.html#section13)
requires a modified version supporting remote interaction to offer its
Corresponding Source prominently to those remote users, without charge.
Distribution can also create source obligations under other license sections.
The offer must correspond to the deployed version and its modifications;
a link to an unrelated upstream branch is not a substitute.

A release should record where users obtain that source and verify the offer
from the deployed interface. This policy does not implement or certify a hosted
source-offer mechanism, a complete dependency-license inventory or a
Blender/Godot/Bevy distribution. Those checks remain release-specific.

The controlling grants are the full licenses and applicable component notices.
For a particular combined release whose compatibility remains uncertain, obtain
a qualified legal review before publishing that combination.

## Proposed permission-only templates

The [licensing proposal and repository audit](licensing/README.md) contains
inactive templates for separately identified, legally eligible materials.
Proprietary adoption is not cleared. These documents do not change this
repository's AGPL grant, earlier permissions or separately licensed components.
AGPL-compliant use of covered NET code requires no separate outreach or
permission. Ownership, contributor authority, third-party compatibility,
release scope and target-market terms must be verified before any operative
permission-only notice is issued.

