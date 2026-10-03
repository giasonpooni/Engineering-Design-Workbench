# Scope

**Status: implemented bounded reference.** Operation `tsde.square-tiled-flow.v1`
computes an exact rational translation-flow prefix on a connected surface built
from 1–32 unit squares. Right and up permutations pair opposite edges by
translation. Genus and cone angles are derived from identified corner classes.
This includes a genus-two L-shaped example and analytical torus fixtures.

The start is strictly interior, direction is nonzero, and start, direction and
duration use canonical reduced rational strings. Affine segments and boundary
intersections are symbolically derived in rational arithmetic. The result retains
directed events, topology, explicit status, invariants and input/result digests.
There is no floating-point approximation or tolerance-based event merging.

Every vertex hit stops before continuation, including regular vertices. The event
budget stops before an omitted gluing. Both produce an explicitly incomplete
prefix. Exceeding an arithmetic or input bound fails without an artifact. The
[contract](CONTRACT.md) fixes these policies and the request/result representation.

## Exclusions

- General polygon gluings, irrational input or continuation through vertices;
- ergodicity, recurrence, asymptotic dynamics or moduli-space conclusions;
- Jacobi-field propagation on smooth curved manifolds;
- SPD covariance geometry or geodesics on arbitrary triangle meshes;
- sensor calibration, state estimation, physical validation or safety certification;
- cryptographic verification or independent execution attestation.

The analytical flat torus is a regression oracle. It is not substituted for the
declared gluing when the surface has noncommuting tile permutations.
