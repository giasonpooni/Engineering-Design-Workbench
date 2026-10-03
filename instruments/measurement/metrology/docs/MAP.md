# Implemented data flow

The host example reads the declared assembly, constructs a simulated raw sample,
applies the declared conversion, retains four separate quality dimensions and
writes a replayable JSONL record. Observation commitments use canonical payload
digests independently of delivery metadata.

The conversion is declared rather than inferred. Simulated counts are not an
LVDT measurement. A downstream digest binding does not establish a beam
measurement or another physical quantity. JSPT is not imported, and no
acquisition firmware is included.
