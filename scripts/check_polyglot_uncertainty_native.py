"""Require actual native covariance propagation; no mocks or fallback providers."""
import argparse
import json
from pathlib import Path
from ciw import polyglot_uncertainty as u
from ciw.telemetry import canonical, digest


def case():
    return {'schema':'notation.linear-map.v1','model':{'owner':'qualification','kind':'synthetic-correlated','digest':digest({'synthetic':'correlated-sum-difference'})},
        'frame':'synthetic-local','inputs':[{'id':'x','unit':'m','scale':1.},{'id':'y','unit':'m','scale':1.}],
        'outputs':[{'id':'difference','unit':'m','scale':1.},{'id':'sum','unit':'m','scale':1.}],
        'baseline':[0.,0.],'delta':[2.,3.],'jacobian_row_major':[1.,-1.,1.,1.],
        'claim_scope':'first-order-mean-response-only','covariance':'not_propagated','may_authorize':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binding',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    if args.output_dir.exists():p.error('Choose a new output directory')
    binding={'runtime':str(args.binding.resolve())}
    c=case(); problem=u.problem(c,u.bind_covariance(c,[[4.,3.],[3.,9.]],provider='synthetic-qualification'))
    artifacts={}; reports={}
    for provider in ('cpp','julia'):
        run=u.execute(problem,provider=provider,bindings=binding)
        retained=json.loads(canonical(run)); cov=u.inspect(retained)
        if cov['matrix']!=[[7.,-5.],[-5.,19.]]:raise ValueError('Exactly representable correlated reference differs')
        fresh=u.replay(retained,bindings=binding)
        artifacts[provider+'-uncertainty-run.json']=retained
        artifacts[provider+'-uncertainty-replay.json']=fresh
        artifacts[provider+'-uncertainty-view.json']=u.export_view(retained)
        # A correlated rank-one input must not become independently noisy outputs.
        common=u.problem(c,u.bind_covariance(c,[[4.,4.],[4.,4.]],provider='synthetic-common-mode'))
        cancelled=u.execute(common,provider=provider,bindings=binding)
        if u.inspect(cancelled)['matrix']!=[[0.,0.],[0.,16.]]:raise ValueError('Common mode did not cancel exactly')
        artifacts[provider+'-common-mode-run.json']=cancelled
        reports[provider]={'calculation_id':run['calculation_id'],'verification_id':run['check']['verification_id'],
            'replayed_calculation_id':fresh['run']['calculation_id'],'common_mode_id':cancelled['calculation_id'],
            'runtime':run['stages'][0]['runtimes']}
    artifacts['uncertainty-qualification.json']={'schema':'notation.linear-uncertainty-qualification.v1',
        'outcome':'passed','scope':'synthetic-correlated-and-common-mode-only','providers':reports,'may_authorize':False}
    args.output_dir.mkdir()
    for name,value in artifacts.items():
        with (args.output_dir/name).open('xb') as f:f.write(canonical(value))
    print(json.dumps(artifacts['uncertainty-qualification.json'],indent=2))

if __name__=='__main__':main()
