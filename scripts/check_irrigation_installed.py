"""Qualify the installed irrigation instrument without importing source code.

Each child uses isolated Python and works outside the checkout. The gate retains
actual command receipts and its small qualification witness. This qualifies a
bounded synthetic investigation, not physical performance or actuation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile


PROVENANCE = """
import importlib.metadata as metadata, importlib.util, json, sys
distribution = metadata.distribution('computational-instrumentation-workbench')
spec = importlib.util.find_spec('ciw')
direct = distribution.read_text('direct_url.json')
print(json.dumps({'distribution': distribution.metadata['Name'],
    'version': distribution.version, 'python': sys.version,
    'interpreter': sys.executable, 'isolated': bool(sys.flags.isolated),
    'ciw_origin': spec.origin, 'package_root': str(distribution.locate_file('ciw')),
    'direct_url': json.loads(direct) if direct else None}))
"""


def _hash(path: Path) -> str:
    value = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _snapshot(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): _hash(path)
            for path in sorted(directory.rglob('*')) if path.is_file()}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def _et0(*, t_min: float, t_max: float, radiation: float, heat_flux: float,
         wind: float, actual_vapour_pressure: float, pressure: float) -> float:
    """Independent daily FAO-56 equation, using declared extrema for e_s."""
    average = (t_min + t_max) / 2
    saturated = lambda temperature: 0.6108 * math.exp(17.27 * temperature / (temperature + 237.3))
    saturation = (saturated(t_min) + saturated(t_max)) / 2
    slope = 4098 * saturated(average) / (average + 237.3) ** 2
    psychrometric = 0.000665 * pressure
    numerator = (0.408 * slope * (radiation - heat_flux)
                 + psychrometric * 900 / (average + 273) * wind
                 * (saturation - actual_vapour_pressure))
    return numerator / (slope + psychrometric * (1 + 0.34 * wind))


class Qualification:
    def __init__(self, python: Path, destination: Path, timeout: float):
        self.python = python
        self.root = destination
        self.timeout = timeout
        self.commands: list[dict] = []
        self.checks: list[dict] = []
        (destination / 'commands').mkdir()

    def require(self, name: str, condition: bool, observed: object = None) -> None:
        self.checks.append({'check': name, 'status': 'PASS' if condition else 'FAIL',
                            'observed': observed})
        if not condition:
            raise ValueError(name)

    def execute(self, name: str, arguments: list[str], expected: int = 0,
                console: Path | None = None) -> dict:
        allowed = ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
                   'TEMP', 'TMP', 'TMPDIR', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA')
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        command = ([str(console), *arguments] if console is not None
                   else [str(self.python), '-I', *arguments])
        stem = f'{len(self.commands) + 1:02d}-{name}'
        stdout_path = self.root / 'commands' / (stem + '.stdout.json')
        stderr_path = self.root / 'commands' / (stem + '.stderr.txt')
        record = {'name': name, 'argv': command, 'cwd': str(self.root),
                  'expected_returncode': expected,
                  'stdout': stdout_path.relative_to(self.root).as_posix(),
                  'stderr': stderr_path.relative_to(self.root).as_posix()}
        self.commands.append(record)
        started = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=self.root, env=environment,
                                       capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_bytes(exc.stdout or b'')
            stderr_path.write_bytes(exc.stderr or b'')
            record.update(returncode=None, status='TIMEOUT', elapsed_s=time.monotonic() - started)
            raise ValueError(f'{name} exceeded {self.timeout:g} seconds') from exc
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        record.update(returncode=completed.returncode, elapsed_s=time.monotonic() - started,
                      stdout_sha256=_hash(stdout_path), stderr_sha256=_hash(stderr_path),
                      status='PASS' if completed.returncode == expected else 'FAIL')
        if completed.returncode != expected:
            raise ValueError(f'{name} returned {completed.returncode}, expected {expected}; see {stderr_path}')
        value = None
        for raw in (completed.stdout, completed.stderr):
            try:
                value = json.loads(raw)
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        if not isinstance(value, dict):
            raise ValueError(f'{name} did not return a JSON object')
        return value

    def net(self, name: str, *arguments: str, expected: int = 0) -> dict:
        return self.execute(name, ['-m', 'ciw.net', 'irrigation', *arguments], expected)

    def unchanged(self, name: str, directory: Path, before: dict) -> None:
        after = _snapshot(directory)
        self.require(name, before == after, {'files': len(after)})


def _wheel_proof(qualification: Qualification, wheel: Path, package_root: Path) -> dict:
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if item.is_dir() or not item.filename.startswith('ciw/'):
                continue
            relative = Path(item.filename).relative_to('ciw')
            if '..' in relative.parts or relative.is_absolute() or item.filename in files:
                raise ValueError('Wheel has an invalid or duplicated ciw path')
            expected = sha256(archive.read(item)).hexdigest()
            installed = package_root / relative
            qualification.require('wheel-byte:' + item.filename,
                                  installed.is_file() and _hash(installed) == expected)
            files[item.filename] = expected
    qualification.require('wheel-package-present', bool(files))
    return {'wheel': str(wheel), 'wheel_sha256': _hash(wheel),
            'ciw_files_matched': len(files), 'files': files}


def _candidate(directory: Path) -> dict:
    rows = _read(directory / 'workspace.json')['results']
    candidates = [row for row in rows if row['operation_id'] == 'irrigation.plan.v1']
    if len(candidates) != 1:
        raise ValueError('Bundle does not contain exactly one planning result')
    return candidates[0]['data']


def _close(actual: float, expected: float, tolerance: float = 1e-10) -> bool:
    return math.isfinite(actual) and abs(actual - expected) <= tolerance * max(1.0, abs(expected))


def _numerics(qualification: Qualification, name: str, request: dict, data: dict) -> None:
    pump = request['pump']
    available = min(pump['rate_m3_h'] * pump['available_hours_per_day'],
                    pump['water_budget_m3_per_day'])
    for zone, initial in zip(request['zones'], data['initial_zones']):
        zone_name = name + ':' + zone['zone_id']
        taw = 1000 * (zone['theta_fc'] - zone['theta_wp']) * zone['root_depth_m']
        qualification.require(zone_name + ':declared-root-capacity',
                              _close(initial['taw_mm'], taw)
                              and _close(initial['raw_mm'], zone['depletion_fraction'] * taw))
        qualification.require(zone_name + ':initial-uncertainty-dimension',
                              _close(initial['standard_uncertainty_mm'],
                                     1000 * zone['root_depth_m']
                                     * math.sqrt(initial['fused_variance_m3_m3_squared'])))
    for weather, day in zip(request['weather'], data['days']):
        day_name = name + ':' + day['date']
        et0 = _et0(t_min=weather['temp_min_c'], t_max=weather['temp_max_c'],
                   pressure=weather['pressure_kpa'], wind=weather['wind_2m_m_s'],
                   radiation=weather['net_radiation_mj_m2_day'],
                   heat_flux=weather['soil_heat_flux_mj_m2_day'],
                   actual_vapour_pressure=weather['actual_vapour_pressure_kpa'])
        qualification.require(day_name + ':independent-daily-FAO56', _close(day['et0_mm'], et0, 1e-12),
                              {'reference_mm': et0, 'candidate_mm': day['et0_mm']})
        allocated = math.fsum(row['allocated_gross_m3'] for row in day['zones'])
        qualification.require(day_name + ':pump-and-water-budget',
                              _close(day['available_gross_m3'], available)
                              and _close(day['allocated_gross_m3'], allocated)
                              and allocated <= available + 1e-10
                              and _close(day['remaining_gross_m3'], available - allocated)
                              and _close(day['pump_hours'], allocated / pump['rate_m3_h'])
                              and day['pump_hours'] <= pump['available_hours_per_day'] + 1e-10)
        for zone, row in zip(request['zones'], day['zones']):
            row_name = day_name + ':' + zone['zone_id']
            gross = row['allocated_net_mm'] * zone['area_m2'] / (1000 * pump['efficiency'])
            qualification.require(row_name + ':gross-and-net-volume',
                                  _close(row['allocated_gross_m3'], gross)
                                  and row['allocated_net_mm'] <= zone['max_daily_net_mm'] + 1e-10
                                  and row['allocated_net_mm'] <= row['requested_net_mm'] + 1e-10
                                  and _close(row['unmet_net_mm'],
                                             row['requested_net_mm'] - row['allocated_net_mm']))
            balance_end = (row['depletion_start_mm'] - row['rainfall_mm'] + row['runoff_mm']
                           - row['allocated_net_mm'] - row['capillary_rise_mm']
                           + row['actual_crop_et_mm'] + row['deep_percolation_mm'])
            qualification.require(row_name + ':independent-water-conservation',
                                  _close(row['depletion_end_mm'], balance_end)
                                  and abs(row['balance_residual_mm']) <= 1e-9,
                                  {'rebuilt_end_mm': balance_end, 'candidate_end_mm': row['depletion_end_mm']})
            qualification.require(row_name + ':screening-is-bounded',
                                  0 <= row['screening_lower_end_mm'] <= row['depletion_end_mm']
                                  <= row['screening_upper_end_mm']
                                  <= 1000 * (zone['theta_fc'] - zone['theta_wp']) * zone['root_depth_m'] + 1e-10)


def _variant(qualification: Qualification, name: str, request: dict,
             planning_status: str | None = None, *, refused: bool = False) -> dict | None:
    _write(qualification.root / (name + '.json'), request)
    expected = 1 if refused else (2 if planning_status in {'REVIEW', 'ABSTAIN', 'UNMET'} else 0)
    response = qualification.net(name, 'run', '--request', name + '.json',
                                 '--output-dir', name, expected=expected)
    if refused:
        qualification.require(name + ':structural-refusal', response['status'] == 'REFUSE')
        qualification.require(name + ':no-bundle-created', not (qualification.root / name).exists())
        return None
    qualification.require(name + ':numerical-qualification', response['status'] == 'LOCAL')
    qualification.require(name + ':planning-status', response['planning_status'] == planning_status,
                          response['planning_status'])
    data = _candidate(qualification.root / name)
    _numerics(qualification, name, request, data)
    return data


def _domain_variants(qualification: Qualification, request: dict) -> dict:
    one_day = deepcopy(request)
    one_day['weather'] = one_day['weather'][:1]
    one_day['telemetry'] = []
    one_day['zones'][1]['soil_measurements']['observations'][0]['calibrated_theta_m3_m3'] = 0.25
    variants = []
    for correlated in (False, True):
        name = 'correlated-replicas' if correlated else 'independent-replicas'
        replica = deepcopy(one_day)
        group = replica['zones'][0]['soil_measurements']
        second = deepcopy(group['observations'][0])
        second.update(observation_id='replica-second', calibrated_theta_m3_m3=0.24)
        group['observations'].append(second)
        if correlated:
            group['covariance'] = [[0.000004, 0.0000032], [0.0000032, 0.000004]]
            expected_mean, expected_variance, expected_weights = 0.23, 0.0000036, [0.5, 0.5]
        else:
            group['covariance'] = [[0.000004, 0.0], [0.0, 0.000016]]
            expected_mean, expected_variance, expected_weights = 0.224, 0.0000032, [0.8, 0.2]
        data = _variant(qualification, name, replica, 'READY')
        initial = data['initial_zones'][0]
        qualification.require(name + ':analytical-two-replica-GLS',
                              _close(initial['fused_theta_m3_m3'], expected_mean, 1e-13)
                              and _close(initial['fused_variance_m3_m3_squared'], expected_variance, 1e-15)
                              and all(_close(actual, expected, 1e-13) for actual, expected in
                                      zip(initial['fusion_weights'], expected_weights)),
                              {'mean': initial['fused_theta_m3_m3'],
                               'variance': initial['fused_variance_m3_m3_squared'],
                               'weights': initial['fusion_weights']})
        variants.append(name)
    limited = deepcopy(one_day)
    limited['zones'][1]['soil_measurements']['observations'][0]['calibrated_theta_m3_m3'] = 0.22
    limited['pump']['water_budget_m3_per_day'] = 30.0
    data = _variant(qualification, 'finite-budget', limited, 'UNMET')
    qualification.require('finite-budget:explicit-zone-priority-and-unmet-demand',
                          _close(data['days'][0]['zones'][0]['allocated_gross_m3'], 30.0)
                          and data['days'][0]['zones'][1]['allocated_gross_m3'] == 0.0
                          and data['days'][0]['unmet_gross_m3'] > 0.0)
    variants.append('finite-budget')
    variant = deepcopy(one_day)
    variant['pump']['available_hours_per_day'] = 2.0
    data = _variant(qualification, 'pump-capacity', variant, 'UNMET')
    qualification.require('pump-capacity:time-window-limits-volume',
                          _close(data['days'][0]['allocated_gross_m3'], 20.0)
                          and _close(data['days'][0]['pump_hours'], 2.0))
    variants.append('pump-capacity')
    variant = deepcopy(one_day)
    variant['zones'][0]['max_daily_net_mm'] = 10.0
    data = _variant(qualification, 'zone-daily-limit', variant, 'UNMET')
    qualification.require('zone-daily-limit:bounded-net-depth',
                          _close(data['days'][0]['zones'][0]['allocated_net_mm'], 10.0)
                          and data['days'][0]['zones'][0]['unmet_net_mm'] > 0.0)
    variants.append('zone-daily-limit')
    for name, field, value in (
        ('stale-observations', 'observed_at', '2026-10-01T00:00:00Z'),
        ('future-observations', 'observed_at', '2026-10-03T01:00:00Z'),
        ('expired-calibration', 'calibrated_until', '2026-10-03T00:00:00Z'),
    ):
        variant = deepcopy(one_day)
        for zone in variant['zones']:
            for observation in zone['soil_measurements']['observations']:
                observation[field] = value
        data = _variant(qualification, name, variant, 'ABSTAIN')
        qualification.require(name + ':holds-all-irrigation-proposals',
                              all(row['allocated_gross_m3'] == row['requested_gross_m3'] == 0.0
                                  and row['projection_is_descriptive_only'] is True
                                  for day in data['days'] for row in day['zones']))
        variants.append(name)
    variant = deepcopy(one_day)
    variant['zones'][1]['soil_measurements']['observations'][0]['calibrated_theta_m3_m3'] = 0.24
    data = _variant(qualification, 'threshold-review', variant, 'REVIEW')
    qualification.require('threshold-review:uncertain-zone-holds-allocation',
                          data['days'][0]['zones'][1]['allocated_gross_m3'] == 0.0
                          and data['days'][0]['zones'][1]['planning_status'] == 'REVIEW')
    variants.append('threshold-review')
    variant = deepcopy(one_day)
    variant['zones'][0]['capillary_rise_mm_per_day'] = 5.0
    variant['weather'][0].update(rainfall_mm=4.0, runoff_mm=2.0)
    data = _variant(qualification, 'declared-capillary-rise', variant, 'READY')
    qualification.require('declared-capillary-rise:upward-input-retained',
                          data['days'][0]['zones'][0]['capillary_rise_mm'] == 5.0)
    variants.append('declared-capillary-rise')
    variant = deepcopy(one_day)
    variant['weather'][0].update(rainfall_mm=200.0, runoff_mm=10.0)
    data = _variant(qualification, 'explicit-deep-percolation', variant, 'READY')
    qualification.require('explicit-deep-percolation:excess-water-is-accounted',
                          all(row['deep_percolation_mm'] > 0.0
                              and row['allocated_net_mm'] == 0.0
                              and row['depletion_end_mm'] == 0.0
                              for row in data['days'][0]['zones']))
    variants.append('explicit-deep-percolation')
    variant = deepcopy(one_day)
    variant['telemetry'] = deepcopy(request['telemetry'])
    variant['telemetry'][0]['observed_flow_m3_h'] = 0.3
    data = _variant(qualification, 'unexpected-closed-flow', variant, 'REVIEW')
    qualification.require('unexpected-closed-flow:residual-hint-without-causal-diagnosis',
                          data['telemetry'][0]['quality_status'] == 'VALID'
                          and data['telemetry'][0]['flow_residual_m3_h'] == 0.3
                          and data['telemetry'][0]['indicators'] == ['unexpected_flow_while_closed']
                          and data['days'][0]['zones'][0]['allocated_net_mm'] == 0.0
                          and data['days'][0]['zones'][0]['planning_status'] == 'REVIEW')
    variants.append('unexpected-closed-flow')
    for name, field, value in (
        ('stale-telemetry', 'observed_at', '2026-10-01T00:00:00Z'),
        ('future-telemetry', 'observed_at', '2026-10-03T01:00:00Z'),
        ('expired-telemetry', 'calibrated_until', '2026-10-03T00:00:00Z'),
    ):
        variant = deepcopy(one_day)
        variant['telemetry'] = deepcopy(request['telemetry'])
        variant['telemetry'][0][field] = value
        data = _variant(qualification, name, variant, 'ABSTAIN')
        qualification.require(name + ':invalid-telemetry-holds-corresponding-zone',
                              data['telemetry'][0]['quality_status'] == 'ABSTAIN'
                              and data['days'][0]['zones'][0]['allocated_net_mm'] == 0.0
                              and data['days'][0]['zones'][0]['planning_status'] == 'ABSTAIN')
        variants.append(name)
    for name in ('singular-covariance', 'wrong-measurand', 'wrong-moisture-unit', 'non-midnight-as-of'):
        variant = deepcopy(one_day)
        group = variant['zones'][0]['soil_measurements']
        if name == 'singular-covariance':
            second = deepcopy(group['observations'][0])
            second['observation_id'] = 'singular-second'
            group['observations'].append(second)
            group['covariance'] = [[0.000004, 0.000004], [0.000004, 0.000004]]
        elif name == 'wrong-measurand':
            group['measurand'] = 'point_probe_water_content'
        elif name == 'wrong-moisture-unit':
            group['unit'] = 'percent'
        else:
            variant['as_of'] = '2026-10-03T12:00:00Z'
        _variant(qualification, name, variant, refused=True)
        variants.append(name)
    return {'cases': variants, 'physical_validation': 'not_established', 'hardware_actuation': 'not_performed'}


def _investigation(qualification: Qualification, console: Path | None = None) -> dict:
    """Exercise the installed lifecycle and independent numerical checks."""
    root = qualification.root
    qualification.net('example', 'example', '--output', 'request.json')
    request = _read(root / 'request.json')
    created = qualification.net('run', 'run', '--request', 'request.json', '--output-dir', 'run')
    qualification.require('numerically-qualified-example', created['status'] == 'LOCAL')
    data = _candidate(root / 'run')
    _numerics(qualification, 'example', request, data)
    qualification.require('published-FAO56-example18-golden-value',
                          _close(data['days'][0]['et0_mm'], 3.879586250204349, 1e-12),
                          {'published_rounded_mm_per_day': 3.9,
                           'unrounded_reference_mm_per_day': 3.879586250204349,
                           'source': 'https://www.fao.org/4/x0490e/x0490e08.htm'})
    bundle = root / 'run'
    before = _snapshot(bundle)
    inspected = qualification.net('inspect', 'inspect', 'run')
    if console is not None:
        console_inspected = qualification.execute('console-launcher-inspect',
                                                  ['irrigation', 'inspect', 'run'], console=console)
        qualification.require('console-launcher-opens-the-same-installed-bundle',
                              console_inspected == inspected)
    verified = qualification.net('fresh-verify', 'verify', 'run', '--output', 'fresh-audit.json')
    verified_again = qualification.net('second-fresh-verify', 'verify', 'run')
    if console is not None:
        console_verified = qualification.execute('console-launcher-fresh-verify',
                                                 ['irrigation', 'verify', 'run'], console=console)
        qualification.require('console-launcher-uses-the-same-installed-verifier',
                              console_verified['recomputed_with_runtime'] == verified['recomputed_with_runtime']
                              and console_verified['result_id'] == inspected['result_id']
                              and console_verified['fresh_verification_id'] != verified['fresh_verification_id']
                              and console_verified['fresh_numerical_verification'] is True)
    retained = ('evidence_id', 'operation_id', 'execution_id', 'result_id',
                'verification_operation_id', 'verification_execution_id', 'verification_id')
    qualification.require('retained-identities-survive-read-and-audit',
                          all(created[key] == inspected[key] == verified[key] == verified_again[key]
                              for key in retained))
    qualification.require('separate-source-operation-execution-result-verification',
                          len({inspected[key] for key in retained}) == len(retained))
    qualification.require('inspection-performs-no-fresh-numerical-verification',
                          inspected['fresh_execution'] is False
                          and inspected['fresh_numerical_verification'] is False)
    qualification.require('verification-invokes-the-independent-verifier',
                          verified['fresh_numerical_verification'] is True
                          and verified_again['fresh_numerical_verification'] is True)
    fresh = ('fresh_verification_id', 'fresh_verification_execution_id', 'fresh_verification_result_id')
    qualification.require('verification-occurrences-are-fresh',
                          all(verified[key] != verified_again[key] for key in fresh)
                          and verified['fresh_verification_id'] != inspected['verification_id'])
    witness = _read(root / 'fresh-audit.json')
    qualification.require('fresh-witness-binds-retained-candidate',
                          witness['fresh_verification_record']['verification_id']
                          == verified['fresh_verification_id']
                          and witness['fresh_verification_record']['candidate_result_id']
                          == inspected['result_id'])
    authority = verified['authority']
    qualification.require('simulation-authority-boundaries',
                          authority['physical_validation'] == 'not_established'
                          and authority['hardware_actuation'] == 'not_performed'
                          and authority['state_admission'] == 'not_performed'
                          and authority['live_sensor_acquisition'] == 'not_performed', authority)
    qualification.unchanged('inspection-and-verification-preserve-bundle', bundle, before)
    replayed = qualification.net('fresh-replay', 'replay', 'run', '--output-dir', 'replay')
    qualification.require('replay-keeps-source-and-creates-new-occurrences',
                          replayed['evidence_id'] == inspected['evidence_id']
                          and all(replayed[key] != inspected[key] for key in
                                  ('execution_id', 'result_id', 'verification_id'))
                          and replayed['reproducible_planning_data'] is True)
    qualification.net('csv-export', 'export-csv', 'run', '--output', 'irrigation.csv')
    with (root / 'irrigation.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        columns = reader.fieldnames
    qualification.require('csv-exports-simulated-zone-day-rows', bool(rows),
                          {'rows': len(rows), 'columns': columns})
    qualification.require('csv-includes-explicit-gross-net-and-relative-time-units',
                          all(key in columns for key in ('allocated_gross_m3', 'allocated_net_mm',
                                                        'pump_window_relative_start_h', 'pump_duration_h',
                                                        'pump_window_relative_end_h', 'balance_residual_mm')))
    qualification.require('csv-complete-zone-day-coverage',
                          len(rows) == len(request['weather']) * len(request['zones']))
    for day_index, day in enumerate(data['days']):
        offset = 0.0
        for priority_index, zone in enumerate(day['zones']):
            row = rows[day_index * len(day['zones']) + priority_index]
            duration = zone['allocated_gross_m3'] / request['pump']['rate_m3_h']
            qualification.require('csv-relative-window:' + day['date'] + ':' + zone['zone_id'],
                                  row['zone_id'] == zone['zone_id'] and row['date'] == day['date']
                                  and int(row['priority_index']) == priority_index
                                  and _close(float(row['pump_window_relative_start_h']), offset)
                                  and _close(float(row['pump_duration_h']), duration)
                                  and _close(float(row['pump_window_relative_end_h']), offset + duration)
                                  and offset + duration <= request['pump']['available_hours_per_day'] + 1e-10)
            offset += duration
    qualification.net('offline-report', 'report', 'run', '--output', 'irrigation.html')
    html_text = (root / 'irrigation.html').read_text(encoding='utf-8')
    qualification.require('offline-report-retains-authority-boundary',
                          '<html' in html_text.lower()
                          and 'not_performed' in html_text and 'not_established' in html_text
                          and "default-src 'none'" in html_text.lower()
                          and '<script' not in html_text.lower())
    qualification.unchanged('replay-and-exports-preserve-bundle', bundle, before)
    malformed = deepcopy(request)
    malformed['unrecognized_parameter'] = True
    _write(root / 'malformed-request.json', malformed)
    refused = qualification.net('malformed-refusal', 'run', '--request', 'malformed-request.json',
                                '--output-dir', 'malformed', expected=1)
    qualification.require('malformed-request-refused', refused['status'] == 'REFUSE')
    qualification.require('malformed-request-creates-no-bundle', not (root / 'malformed').exists())
    repeated = qualification.net('create-only-run', 'run', '--request', 'request.json',
                                 '--output-dir', 'run', expected=1)
    qualification.require('existing-run-refused', repeated['status'] == 'REFUSE')
    csv_before = _hash(root / 'irrigation.csv')
    repeated = qualification.net('create-only-csv', 'export-csv', 'run',
                                 '--output', 'irrigation.csv', expected=1)
    qualification.require('existing-csv-refused-with-original-preserved',
                          repeated['status'] == 'REFUSE' and _hash(root / 'irrigation.csv') == csv_before)
    html_before = _hash(root / 'irrigation.html')
    repeated = qualification.net('create-only-report', 'report', 'run',
                                 '--output', 'irrigation.html', expected=1)
    qualification.require('existing-report-refused-with-original-preserved',
                          repeated['status'] == 'REFUSE' and _hash(root / 'irrigation.html') == html_before)
    witness_before = _hash(root / 'fresh-audit.json')
    repeated = qualification.net('create-only-audit', 'verify', 'run',
                                 '--output', 'fresh-audit.json', expected=1)
    qualification.require('existing-audit-refused-with-original-preserved',
                          repeated['status'] == 'REFUSE' and _hash(root / 'fresh-audit.json') == witness_before)
    tampered = root / 'tampered'
    tampered.mkdir()
    for filename in ('request.json', 'workspace.json', 'verification.json'):
        (tampered / filename).write_bytes((bundle / filename).read_bytes())
    workspace = _read(tampered / 'workspace.json')
    candidate = next(row for row in workspace['results'] if row['operation_id'] == 'irrigation.plan.v1')
    candidate['data']['days'][0]['allocated_gross_m3'] += 1.0
    (tampered / 'workspace.json').write_text(json.dumps(workspace, allow_nan=False), encoding='utf-8')
    refused = qualification.net('tampered-inspection', 'inspect', 'tampered', expected=1)
    qualification.require('tampered-result-seal-refused', refused['status'] == 'REFUSE')
    refused = qualification.net('tampered-export', 'export-csv', 'tampered',
                                '--output', 'blocked-tampered.csv', expected=1)
    qualification.require('tampered-result-cannot-be-exported',
                          refused['status'] == 'REFUSE' and not (root / 'blocked-tampered.csv').exists())
    qualification.unchanged('create-only-refusals-preserve-bundle', bundle, before)
    variants = _domain_variants(qualification, request)
    return {'retained_identities': {key: inspected[key] for key in retained},
            'planning_status': inspected['planning_status'],
            'explicit_fresh_audit_occurrences': 3 if console is not None else 2,
            'replay_new_occurrences': True, 'csv_rows': len(rows), 'csv_columns': columns,
            'retained_bundle_sha256': before, 'domain_variants': variants}


def qualify(python: Path, destination: Path, *, console: Path | None = None,
            expected_wheel: Path | None = None,
            timeout: float = 120) -> dict:
    python = python.absolute()
    if not python.is_file():
        raise ValueError('Installed Python executable is unavailable')
    if console is not None:
        console = console.absolute()
        if not console.is_file():
            raise ValueError('Installed net executable is unavailable')
    destination = destination.absolute()
    checkout = Path(__file__).resolve().parents[1]
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output directory already exists; choose a new path')
    if destination.resolve().is_relative_to(checkout):
        raise ValueError('Qualification output must be outside the source checkout')
    destination.mkdir(parents=True, exist_ok=False)
    qualification = Qualification(python, destination.resolve(), timeout)
    report = {'schema': 'ciw.irrigation-installed-qualification.v1', 'status': 'FAIL',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'bounded installed synthetic irrigation investigation',
              'physical_validation': 'not_established', 'hardware_actuation': 'not_performed',
              'commands': qualification.commands, 'checks': qualification.checks}
    try:
        provenance = qualification.execute('installed-provenance', ['-c', PROVENANCE])
        report['installed_package'] = provenance
        qualification.require('isolated-interpreter', provenance['isolated'] is True)
        package_root = Path(provenance['package_root']).resolve(strict=True)
        editable = (provenance.get('direct_url') or {}).get('dir_info', {}).get('editable')
        qualification.require('installed-package-without-source-fallback',
                              editable is not True and Path(provenance['ciw_origin']).resolve()
                              == package_root / '__init__.py'
                              and not package_root.is_relative_to(checkout))
        report['wheel_byte_proof'] = (_wheel_proof(qualification, expected_wheel, package_root)
                                      if expected_wheel else {'status': 'not_requested'})
        report['investigation'] = _investigation(qualification, console)
        report['status'] = 'PASS'
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        report['failure'] = {'type': type(exc).__name__, 'reason': str(exc)}
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    _write(qualification.root / 'qualification.json', report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, default=Path(sys.executable),
                        help='Interpreter containing the installed wheel')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='New output directory outside the checkout')
    parser.add_argument('--net', type=Path, help='Also exercise this installed console launcher')
    parser.add_argument('--expected-wheel', '--wheel', type=Path,
                        help='Optional exact installed package-byte proof')
    parser.add_argument('--timeout', type=float, default=120, help='Per-command limit in seconds (1–300)')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error('timeout must be between 1 and 300 seconds')
    try:
        report = qualify(args.python, args.output_dir, console=args.net, expected_wheel=args.expected_wheel,
                         timeout=args.timeout)
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'REFUSE', 'reason': str(exc)}))
        return 2
    print(json.dumps({'status': report['status'],
                      'qualification': str(args.output_dir.absolute() / 'qualification.json'),
                      'commands': len(report['commands']), 'checks': len(report['checks']),
                      'physical_validation': report['physical_validation'],
                      'hardware_actuation': report['hardware_actuation']}, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
