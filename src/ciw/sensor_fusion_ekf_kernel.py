"""Fixed pinned-provider program for the declared Euclidean error-state EKF.

The subprocess imports only GSIE and JSPT. NET validates and retains the input,
runtime, evidence, and operation occurrences around this program.
"""

BOOTSTRAP = r'''
import json, math, sys
from fractions import Fraction
from hashlib import sha256
import numpy as np

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from geometric_state_inference import StatePrior, Observation, LinearDynamics, LinearObservation, predict, update
from geometric_state_inference.geometry import EuclideanGeometry
from sensitivity.reference_models import affine_map, quadratic_form_gradient, componentwise_exp, polar_from_cartesian
from sensitivity.composition import compose
from sensitivity.coordinates import check_mean_fidelity

METHOD = 'jspt.analytic-gsie.error-state-ekf.v1'


def identity(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode()
    return 'sha256:' + sha256(encoded).hexdigest()


def finite(value, shape, name):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.all(np.isfinite(result)):
        raise ValueError(name + ' must retain its declared finite shape')
    return result


def fraction(value):
    return Fraction.from_float(float(value))


def fidelity(exact, observed, name):
    """Bounded exact binary64 reference; zero and tiny coefficients are kept."""
    actual = np.asarray(observed, dtype=float).reshape(-1)
    if len(exact) != actual.size or not np.all(np.isfinite(actual)):
        raise ValueError(name + ' exact-reference shape or finite domain differs')
    for reference, value in zip(exact, actual):
        try:
            representable = float(reference)
        except OverflowError as exc:
            raise ValueError(name + ' exact reference exceeds binary64') from exc
        if not math.isfinite(representable) or (reference and representable == 0):
            raise ValueError(name + ' exact reference loses its nonzero binary64 domain')
        if not reference:
            if value != 0:
                raise ValueError(name + ' changes an exact zero')
        elif value == 0 or abs(fraction(value) - reference) > abs(reference) * Fraction(1, 100000000):
            raise ValueError(name + ' loses componentwise fidelity (tolerance 1e-8)')


def affine_reference(parameters, center):
    x = [fraction(value) for value in center]
    return [sum((fraction(a) * b for a, b in zip(row, x)), Fraction(0)) + fraction(offset)
            for row, offset in zip(parameters['matrix'], parameters['offset'])]


def evaluate(declaration, center, output_size, *, need_jacobian=True):
    x = finite(center, (n,), 'model center')
    family, parameters = declaration['family'], declaration['parameters']
    if family == 'affine.v1':
        model = affine_map(parameters['matrix'], parameters['offset'])
    elif family == 'quadratic.v1':
        model = quadratic_form_gradient(hess=parameters['hessian'], grad=parameters['gradient'])
    elif family == 'componentwise-exp.v1':
        model = componentwise_exp(dim=n)
    elif family == 'planar-range.v1':
        projection = affine_map(parameters['position_matrix'], -np.asarray(parameters['anchor'], dtype=float))
        with np.errstate(all='raise'):
            projected = finite(projection.evaluate(x), (2,), 'range projection')
        projection_parameters = {'matrix': parameters['position_matrix'],
                                 'offset': [-value for value in parameters['anchor']]}
        fidelity(affine_reference(projection_parameters, x), projected, 'range projection')
        with np.errstate(all='raise'):
            radius = float(np.hypot(projected[0], projected[1]))
        if not math.isfinite(radius) or radius < parameters['minimum_range']:
            raise ValueError('range center lies outside its declared minimum_range domain')
        model = compose([projection, polar_from_cartesian(), affine_map([[1.0, 0.0]], [0.0])])
    else:
        raise ValueError('unsupported fixed analytical model family')
    with np.errstate(all='raise'):
        value = finite(model.evaluate(x), (output_size,), 'model value')
        jacobian = (finite(model.analytical_jacobian(x), (output_size, n), 'model Jacobian')
                    if need_jacobian else None)
    if family == 'affine.v1':
        fidelity(affine_reference(parameters, x), value, 'affine value')
        if need_jacobian:
            fidelity([fraction(a) for row in parameters['matrix'] for a in row], jacobian, 'affine Jacobian')
    elif family == 'quadratic.v1':
        exact_x = [fraction(a) for a in x]
        hessian, gradient = parameters['hessian'], parameters['gradient']
        linear = sum((fraction(g) * a for g, a in zip(gradient, exact_x)), Fraction(0))
        quadratic = sum((a * fraction(h) * b for a, row in zip(exact_x, hessian)
                         for h, b in zip(row, exact_x)), Fraction(0)) / 2
        fidelity([quadratic + linear], value, 'quadratic value')
        if need_jacobian:
            exact_jacobian = [sum((fraction(h) * a for h, a in zip(row, exact_x)), Fraction(0)) + fraction(g)
                              for row, g in zip(hessian, gradient)]
            fidelity(exact_jacobian, jacobian, 'quadratic Jacobian')
    return value, jacobian


def state_identity(phase, inputs, previous, time, mean, covariance, linearization):
    return identity({'schema': 'ciw.sensor-fusion-ekf-state.v1', 'phase': phase,
        'method': METHOD, 'state_contract': state, 'batch_id': inputs['batch_id'],
        'configuration_id': inputs['configuration_id'], 'predecessor_state_id': previous,
        'time': time, 'mean': mean.tolist(), 'covariance': covariance.tolist(),
        'linearization': linearization})


def snapshot(result):
    return {'state_id': result.state_id, 'mean': result.mean.tolist(),
            'covariance': result.covariance.tolist(), 'replay': result.replay_snapshot}


def observations(batch, inputs, center, *, need_jacobian=True):
    sensors = {sensor['sensor_id']: sensor for sensor in inputs['profile']['sensors']}
    values, jacobians = [], []
    for observation in batch['observations']:
        sensor = sensors[observation['sensor_id']]
        value, jacobian = evaluate(sensor['model'], center, len(sensor['quantity_ids']),
                                   need_jacobian=need_jacobian)
        values.append(value)
        if need_jacobian:
            jacobians.append(jacobian)
    return np.concatenate(values), np.vstack(jacobians) if need_jacobian else None


request = json.loads(sys.stdin.buffer.read())
source, resolved = request['source'], request['resolved']
state = source['configuration']['state']
n = len(state['quantity_ids'])
if not 1 <= n <= 16 or len(source['batches']) != len(resolved) or not 1 <= len(resolved) <= 16:
    raise ValueError('model and batch bounds differ')
geometry = EuclideanGeometry()
prior = StatePrior(**source['prior'], frame_id=state['frame'], units=state['units'],
                   state_id=request['initial_state_id'])
results = []
for index, (batch, inputs) in enumerate(zip(source['batches'], resolved)):
    previous_id = prior.state_id
    dynamics_value, dynamics_jacobian = evaluate(batch['dynamics']['model'], prior.mean, n)
    error_prior_id = identity({'schema': 'ciw.sensor-fusion-ekf-error-prior.v1',
        'phase': 'prediction-prior', 'method': METHOD, 'predecessor_state_id': previous_id,
        'batch_id': inputs['batch_id']})
    error_prior = StatePrior(prior.time, np.zeros(n), prior.covariance,
        state['frame'], state['units'], error_prior_id)
    dynamics_id = identity({'schema': 'ciw.sensor-fusion-ekf-linearized-dynamics.v1',
        'predecessor_state_id': previous_id, 'batch_id': inputs['batch_id'],
        'center': prior.mean.tolist(), 'model': batch['dynamics']})
    kernel_prediction = predict(error_prior, LinearDynamics(dynamics_jacobian,
        batch['dynamics']['process_covariance'], dynamics_id), batch['time'], geometry)
    prediction_linearization = {'dynamics_center': prior.mean.tolist(),
        'dynamics_value': dynamics_value.tolist(), 'dynamics_jacobian': dynamics_jacobian.tolist(),
        'predicted_mean': dynamics_value.tolist(), 'predicted_covariance': kernel_prediction.covariance.tolist(),
        'kernel_prediction': snapshot(kernel_prediction)}
    predicted_id = state_identity('prediction', inputs, previous_id, batch['time'],
        dynamics_value, kernel_prediction.covariance, prediction_linearization)
    predicted = StatePrior(batch['time'], dynamics_value, kernel_prediction.covariance,
                           state['frame'], state['units'], predicted_id)
    linearization = {**prediction_linearization, 'observation_value': [], 'observation_jacobian': [],
        'correction': np.zeros(n).tolist(), 'post_observation_value': [], 'kernel_update': None}
    diagnostics = {'status': 'prediction_only', 'innovation': [], 'innovation_covariance': [],
                   'residual': [], 'linearized_residual': [], 'nis': None}
    prior = predicted
    if inputs['values']:
        observation_value, observation_jacobian = observations(batch, inputs, predicted.mean)
        with np.errstate(all='raise'):
            innovation = finite(np.asarray(inputs['values'], dtype=float) - observation_value,
                                observation_value.shape, 'innovation')
        frame = inputs['records'][0]['frame']
        observation_id = identity({'schema': 'ciw.sensor-fusion-ekf-linearized-observation.v1',
            'batch_id': inputs['batch_id'], 'predecessor_state_id': predicted_id,
            'values': inputs['values'], 'observation_value': observation_value.tolist(),
            'innovation': innovation.tolist()})
        observation_model_id = identity({'schema': 'ciw.sensor-fusion-ekf-linearized-observation-model.v1',
            'batch_id': inputs['batch_id'], 'configuration_id': inputs['configuration_id'],
            'predecessor_state_id': predicted_id, 'matrix': observation_jacobian.tolist()})
        observation = Observation(batch['time'], innovation, batch['measurement_noise']['matrix'],
            frame, inputs['units'], observation_id, tuple(inputs['evidence_refs']))
        model = LinearObservation(observation_jacobian, observation_model_id,
            measurement_geometry=geometry, measurement_units=inputs['units'], measurement_frame_id=frame)
        with np.errstate(all='raise'):
            kernel_update = update(kernel_prediction, observation, model, geometry)
        with np.errstate(all='raise'):
            posterior_mean = finite(predicted.mean + kernel_update.mean, (n,), 'posterior mean')
            recovered_correction = posterior_mean - predicted.mean
        check_mean_fidelity(kernel_update.mean, recovered_correction, np.zeros((n, n)), 'EKF correction')
        StatePrior(batch['time'], posterior_mean, kernel_update.covariance,
                   state['frame'], state['units'], predicted_id)
        post_observation_value, _ = observations(batch, inputs, posterior_mean, need_jacobian=False)
        with np.errstate(all='raise'):
            residual = finite(np.asarray(inputs['values'], dtype=float) - post_observation_value,
                              observation_value.shape, 'nonlinear posterior residual')
        linearization.update({'observation_value': observation_value.tolist(),
            'observation_jacobian': observation_jacobian.tolist(), 'correction': kernel_update.mean.tolist(),
            'post_observation_value': post_observation_value.tolist(), 'kernel_update': snapshot(kernel_update)})
        diagnostics = {'status': 'updated', 'innovation': kernel_update.innovation.tolist(),
            'innovation_covariance': kernel_update.innovation_covariance.tolist(),
            'residual': residual.tolist(), 'linearized_residual': kernel_update.residual.tolist(), 'nis': kernel_update.nis}
        state_id = state_identity('update', inputs, predicted_id, batch['time'],
            posterior_mean, kernel_update.covariance, linearization)
        prior = StatePrior(batch['time'], posterior_mean, kernel_update.covariance,
                           state['frame'], state['units'], state_id)
    results.append({'batch_index': index, 'configuration_id': inputs['configuration_id'],
        'configuration_ref': batch['configuration_ref'], 'epoch_index': inputs['epoch_index'],
        'time': prior.time, 'predecessor_state_id': previous_id, 'predicted_state_id': predicted_id,
        'state_id': prior.state_id, 'mean': prior.mean.tolist(), 'covariance': prior.covariance.tolist(),
        'diagnostics': diagnostics, 'observation_refs': inputs['evidence_refs'],
        'observation_order': inputs['order'], 'linearization': linearization})
print(json.dumps({'schema': 'ciw.sensor-fusion-ekf-result.v1', 'method': METHOD,
    'initial_state_id': request['initial_state_id'], 'state_contract': state,
    'estimates': results, 'authority': request['authority']}, allow_nan=False))
'''
