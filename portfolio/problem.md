# Problem specimen

Two systems observe events in different clock coordinates. Downstream analysis needs
one explicitly identified reference-clock coordinate without destroying the original
device timestamp or silently inventing a synchronization model.

ClockSync therefore solves one deliberately bounded problem:

> Given a source timestamp, a caller-supplied affine clock map, and their joint
> covariance, compute the corresponding reference-clock event coordinate and
> first-order timing variance.

The canonical specimen uses the shipped `offset` request. It is synthetic and is
not metrological evidence from a physical device.

The instrument refuses work when the model/frame identity does not match, the
timestamp is outside the model applicability interval, synchronization evidence is
required but absent, covariance is invalid, or numeric inputs are malformed.
