"""Strict, aligned north-up raster contracts for small reference workloads."""
from copy import deepcopy
import math
import numpy as np

MAX_CELLS = 65536

def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Unexpected or missing fields; expected " + str(sorted(expected)))

def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e100:
        raise ValueError("Require finite bounded numeric values, not booleans")
    return float(value)

def text(value):
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise ValueError("Require bounded nonempty text")
    return value

def raster(value):
    keys(value, {'values', 'crs', 'transform', 'unit'})
    text(value['crs']); text(value['unit'])
    t = value['transform']
    if type(t) is not list or len(t) != 6:
        raise ValueError("Transform must be [x_origin, dx, 0, y_origin, 0, dy]")
    t = [number(x) for x in t]
    if t[1] <= 0 or t[5] >= 0 or t[2] != 0 or t[4] != 0:
        raise ValueError("Require north-up grid: positive dx, negative dy, no rotation")
    rows = value['values']
    if type(rows) is not list or not rows or type(rows[0]) is not list or not rows[0]:
        raise ValueError("Require nonempty rectangular raster")
    width = len(rows[0])
    if len(rows)*width > MAX_CELLS:
        raise ValueError("Raster exceeds 65536-cell bound")
    if any(type(row) is not list or len(row) != width for row in rows):
        raise ValueError("Require rectangular raster")
    return np.array([[np.nan if x is None else number(x) for x in row] for row in rows], dtype=float)

def aligned(*rasters):
    arrays = [raster(r) for r in rasters]
    if any(a.shape != arrays[0].shape or r['crs'] != rasters[0]['crs'] or
           r['transform'] != rasters[0]['transform'] for r,a in zip(rasters, arrays)):
        raise ValueError("Raster CRS, transform and shape must match exactly; reproject upstream")
    return arrays

def output_raster(template, values, unit=None):
    result = deepcopy(template)
    a = np.asarray(values, dtype=float)
    if np.isinf(a).any():
        raise ValueError("Numerical overflow in raster result")
    result['values'] = [[None if np.isnan(x) else float(x) for x in row] for row in a]
    if unit is not None:
        result['unit'] = unit
    return result

def output_number(value):
    """Finite retained scalar, using the NET JSON boundary's output bound."""
    if type(value) not in (int, float) or abs(value) > 1e150 or not math.isfinite(value):
        raise ValueError("Require a finite bounded output number, not a boolean")
    return float(value)

def validate_assumptions(value):
    if type(value) is not list or not 1 <= len(value) <= 32:
        raise ValueError("Require a nonempty bounded list of output assumptions")
    for item in value:
        text(item)

def validate_output_raster(template, result, unit):
    """Check a retained raster's representation; never recalculate its field."""
    shape = raster(template).shape
    keys(result, {'values', 'crs', 'transform', 'unit'})
    text(result['crs']); text(result['unit'])
    transform = result['transform']
    if type(transform) is not list or len(transform) != 6:
        raise ValueError("Invalid retained raster transform")
    for value in transform:
        number(value)
    if (result['crs'] != template['crs'] or transform != template['transform'] or
            result['unit'] != unit):
        raise ValueError("Retained raster CRS, transform or unit differs from the operation contract")
    rows = result['values']
    if (type(rows) is not list or len(rows) != shape[0] or
            any(type(row) is not list or len(row) != shape[1] for row in rows)):
        raise ValueError("Retained raster shape differs from the operation contract")
    return np.array([[np.nan if x is None else output_number(x) for x in row] for row in rows], dtype=float)

def metric(r):
    crs = text(r['crs'])
    if not crs.startswith('LOCAL_METRE:') or not crs[len('LOCAL_METRE:'):].strip():
        raise ValueError("This metric reference requires an explicit LOCAL_METRE: frame; project upstream")

def example_raster(values, unit='1'):
    return {'values': values, 'crs':'LOCAL_METRE:synthetic-campus',
            'transform':[0,10,0,30,0,-10], 'unit':unit}
