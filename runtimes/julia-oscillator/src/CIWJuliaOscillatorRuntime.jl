"""Package entry point for the named, pinned oscillator worker environment.

The framed worker remains oscillator_worker.jl and is launched explicitly by
CIW. Loading/precompiling this environment does not start a worker, solve an
ODE, register an operation, or change any retained runtime identity.
"""
module CIWJuliaOscillatorRuntime
end
