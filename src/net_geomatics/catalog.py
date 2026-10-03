"""Fixed provider catalog. Data cannot import or select executable code paths."""
from . import gis, earth_observation, radiometry, urban

MODULES = (gis, earth_observation, radiometry, urban)

def _build_catalog(modules):
    operations, examples = {}, {}
    for module in modules:
        if set(module.OPERATIONS) != set(module.EXAMPLES):
            raise ValueError('Each geomatics provider must supply exactly one example per operation')
        duplicates = set(operations).intersection(module.OPERATIONS)
        if duplicates:
            raise ValueError('Duplicate geomatics operation IDs: ' + ', '.join(sorted(duplicates)))
        operations.update(module.OPERATIONS)
        examples.update(module.EXAMPLES)
    return operations, examples

OPERATIONS, EXAMPLES = _build_catalog(MODULES)
OUTPUT_VALIDATORS = {key: value for module in MODULES for key, value in module.OUTPUT_VALIDATORS.items()}
if set(OUTPUT_VALIDATORS) != set(OPERATIONS):
    raise ValueError('Every geomatics operation requires a fixed saved-output validator')

def validate_output(operation_id, parameters, output):
    if operation_id not in OUTPUT_VALIDATORS:
        raise ValueError('Unknown geomatics output schema')
    OUTPUT_VALIDATORS[operation_id](parameters, output)

def execute(operation_id, parameters):
    if operation_id not in OPERATIONS:
        raise ValueError('Unknown geomatics operation')
    return OPERATIONS[operation_id](parameters)
