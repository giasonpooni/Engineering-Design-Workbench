#!/usr/bin/env julia
module CIWNativeInteropWorker

# Capture package diagnostics; stdout is reserved for framed data.
redirect_stdout(stderr) do
    @eval using JSON3, SHA, LinearAlgebra
    @eval using ControlSystemsBase
    @eval using JuMP, HiGHS
    include(joinpath(@__DIR__, "..", "julia-oscillator", "oscillator_worker.jl"))
end

const OLD = CIWJuliaOscillatorWorker
const MAX_FRAME = 1024 * 1024
const PROFILES = ["affine-binary64.v1", "affine-d256.v1", "oscillator-tsit5.v1",
                  "control-oscillator.v1", "design-qp.v1"]
const MODEL_KEYS = ["model", "initial_state", "time_s", "solver"]
const GEOMETRIC = Dict("layout" => "row-major", "input_units" => "dimensionless",
    "output_units" => "dimensionless", "frame" => "declared-cartesian", "clock" => "not-applicable")
const PHYSICAL = Dict("layout" => "row-major", "input_units" => "SI", "output_units" => "SI",
    "frame" => "one-dimensional-inertial", "clock" => "declared-simulation-time")

keys_exact(value, expected) = OLD.keys_exact(value, expected)
number(value, bound=1.0e4) = OLD.number(value, -bound, bound)
function integer(value, lo, hi)
    value isa Integer && !(value isa Bool) && lo <= value <= hi ||
        throw(ArgumentError("integer outside declared bounds"))
    Int64(value)
end
function identifier(value)
    value isa String && occursin(r"^[A-Za-z0-9_.:-]{1,128}$", value) ||
        throw(ArgumentError("invalid transport or execution identifier"))
    value
end
function vector(value, count; exact=false, bound=1.0e4)
    value isa AbstractVector && length(value) == count || throw(ArgumentError("invalid array shape"))
    exact ? [integer(v, -4096, 4096) for v in value] : [number(v,bound) for v in value]
end
function dimensions(p)
    integer(p["rows"], 1, 8), integer(p["columns"], 1, 8)
end

function read_frame(io)
    header = read(io, 4)
    isempty(header) && return nothing
    length(header) == 4 || throw(ArgumentError("truncated frame header"))
    count = (Int(header[1]) << 24) | (Int(header[2]) << 16) | (Int(header[3]) << 8) | Int(header[4])
    1 <= count <= MAX_FRAME || throw(ArgumentError("empty or oversized frame"))
    bytes = read(io, count)
    length(bytes) == count || throw(ArgumentError("truncated frame payload"))
    bytes
end
function write_frame(io, value)
    bytes = Vector{UInt8}(codeunits(JSON3.write(value)))
    count = length(bytes)
    1 <= count <= MAX_FRAME || throw(ArgumentError("oversized response"))
    write(io, UInt8[(count >> 24) & 0xff, (count >> 16) & 0xff, (count >> 8) & 0xff, count & 0xff])
    write(io, bytes)
    flush(io)
end
function decode(bytes)
    isvalid(String, bytes) || throw(ArgumentError("request is not UTF-8"))
    JSON3.read(String(bytes), Dict{String,Any})
end
function identity()
    filehash(path) = "sha256:" * bytes2hex(sha256(read(normpath(path))))
    Dict("schema" => "ciw.native-interop-julia-identity.v1", "julia_version" => string(VERSION),
        "platform" => string(Sys.MACHINE), "threads" => Threads.nthreads(),
        "worker_sha256" => filehash(@__FILE__), "project_sha256" => filehash(joinpath(@__DIR__, "Project.toml")),
        "manifest_sha256" => filehash(joinpath(@__DIR__, "Manifest.toml")),
        "oscillator_worker_sha256" => filehash(joinpath(@__DIR__, "..", "julia-oscillator", "oscillator_worker.jl")),
        "packages" => Dict("ControlSystemsBase" => string(pkgversion(ControlSystemsBase)),
            "JuMP" => string(pkgversion(JuMP)), "HiGHS" => string(pkgversion(HiGHS)),
            "JSON3" => string(pkgversion(JSON3)),
            "OrdinaryDiffEqTsit5" => string(pkgversion(OLD.OrdinaryDiffEqTsit5)),
            "SciMLBase" => string(pkgversion(OLD.SciMLBase))))
end

function affine(p, exact)
    keys_exact(p, ["rows", "columns", "a_row_major", "b", "x0", "delta_x"])
    m, n = dimensions(p)
    a = vector(p["a_row_major"], m*n; exact, bound=1.0e6)
    b = vector(p["b"], m; exact, bound=1.0e6)
    x = vector(p["x0"], n; exact, bound=1.0e6)
    delta = vector(p["delta_x"], n; exact, bound=1.0e6)
    add = exact ? Base.Checked.checked_add : +
    mul = exact ? Base.Checked.checked_mul : *
    zero_value = exact ? Int64(0) : 0.0
    contributions = [mul(a[(i-1)*n+j], delta[j]) for i in 1:m for j in 1:n]
    y0, dy, model = fill(zero_value,m), fill(zero_value,m), fill(zero_value,m)
    for i in 1:m
        offset = exact ? mul(b[i], Int64(256)) : b[i]
        y0[i] = model[i] = offset
        for j in 1:n
            idx = (i-1)*n+j
            y0[i] = add(y0[i], mul(a[idx], x[j]))
            dy[i] = add(dy[i], contributions[idx])
            # Shifted exact numerators may reach 8192; no input-grid rounding.
            model[i] = add(model[i], mul(a[idx], add(x[j], delta[j])))
        end
    end
    predicted = [add(y0[i], dy[i]) for i in 1:m]
    residual = exact ? Base.Checked.checked_sub.(model,predicted) : model .- predicted
    Dict("rows" => m, "columns" => n, "baseline_output" => y0, "contributions" => contributions,
        "predicted_delta" => dy, "predicted_output" => predicted, "model_output" => model,
        "residual" => residual, "denominator" => (exact ? 65536 : 1))
end

function oscillator(p, request_id)
    keys_exact(p, MODEL_KEYS)
    OLD.solve_request(merge(p, Dict("schema" => OLD.REQUEST_SCHEMA, "operation_id" => OLD.OPERATION)), request_id)
end
function control(p)
    keys_exact(p, ["model", "initial_state", "time_s"])
    validated = merge(p, Dict("schema" => OLD.REQUEST_SCHEMA, "operation_id" => OLD.OPERATION,
        "solver" => Dict("abstol" => 1e-10, "reltol" => 1e-10, "maxiters" => 100000)))
    OLD.validate(validated)
    times = Float64.(p["time_s"])
    dt = times[2] - times[1]
    all(isapprox(times[i], (i-1)*dt; atol=1e-12, rtol=1e-12) for i in eachindex(times)) ||
        throw(ArgumentError("control profile requires a uniform grid; no resampling is performed"))
    omega, gamma, mass = Float64(p["model"]["omega_0_rad_s"]), Float64(p["model"]["gamma_s_inv"]), Float64(p["model"]["mass_kg"])
    initial = Float64[p["initial_state"]["q0_m"], p["initial_state"]["v0_m_s"]]
    a = [0.0 1.0; -omega^2 -2gamma]
    b = reshape([0.0, 1.0/mass], 2, 1)
    system = ControlSystemsBase.ss(a, b, Matrix{Float64}(I,2,2), zeros(2,1))
    response = ControlSystemsBase.lsim(system, zeros(1,length(times)), times; x0=initial, method=:zoh)
    q = vec(response.y[1,:])
    v = vec(response.y[2,:])
    energy = 0.5mass .* (v.^2 .+ omega^2 .* q.^2)
    all(isfinite, q) && all(isfinite, v) && all(isfinite, energy) || throw(ErrorException("nonfinite control response"))
    Dict("time_s" => times, "q_m" => q, "v_m_s" => v, "energy_j" => energy,
        "state_order" => ["q", "v"], "solver" => Dict("algorithm" => "ControlSystemsBase.lsim",
            "method" => "zoh", "sample_interval_s" => dt, "retcode" => "Success",
            "controlsystemsbase_version" => string(pkgversion(ControlSystemsBase))))
end

function quadratic(p)
    keys_exact(p, ["rows", "columns", "j_row_major", "y0", "target", "regularization", "lower", "upper", "max_iterations"])
    m, n = dimensions(p)
    flat = vector(p["j_row_major"], m*n)
    j = [flat[(i-1)*n+k] for i in 1:m, k in 1:n]
    r0 = vector(p["y0"], m) .- vector(p["target"], m)
    lo, hi = vector(p["lower"],n), vector(p["upper"],n)
    all(lo .<= hi) || throw(ArgumentError("inverted bounds"))
    lambda = OLD.number(p["regularization"], 1e-6, 1e4)
    maxiters = integer(p["max_iterations"], 0, 10000)
    options = Dict{String,Any}("threads" => 1, "time_limit" => 10.0, "qp_iteration_limit" => maxiters,
        "primal_feasibility_tolerance" => 1e-9, "dual_feasibility_tolerance" => 1e-9, "random_seed" => 0)
    model = JuMP.Model(HiGHS.Optimizer)
    JuMP.set_silent(model)
    for (key,value) in options
        JuMP.set_optimizer_attribute(model,key,value)
    end
    JuMP.@variable(model, lo[k] <= d[k=1:n] <= hi[k])
    JuMP.@objective(model, Min, 0.5sum((r0[i]+sum(j[i,k]*d[k] for k in 1:n))^2 for i in 1:m)+0.5lambda*sum(d[k]^2 for k in 1:n))
    JuMP.optimize!(model)
    termination, primal = JuMP.termination_status(model), JuMP.primal_status(model)
    termination == JuMP.MOI.OPTIMAL && primal == JuMP.MOI.FEASIBLE_POINT && JuMP.has_values(model) ||
        throw(ErrorException("NUMERICAL_FAILURE: termination=$termination; primal=$primal"))
    delta = JuMP.value.(d)
    objective = JuMP.objective_value(model)
    all(isfinite,delta) && isfinite(objective) || throw(ErrorException("nonfinite QP response"))
    Dict("delta" => delta, "objective_value" => objective, "lower_residual" => max.(lo .- delta,0.0),
        "upper_residual" => max.(delta .- hi,0.0), "gradient" => transpose(j)*(r0+j*delta)+lambda*delta,
        "solver" => Dict("name" => "HiGHS", "version" => string(pkgversion(HiGHS)),
            "library_version" => JuMP.MOI.get(JuMP.backend(model),JuMP.MOI.SolverVersion()),
            "jump_version" => string(pkgversion(JuMP)),
            "termination_status" => string(termination), "primal_status" => string(primal),
            "options" => options, "solve_seconds" => JuMP.solve_time(model)))
end

function execute(request)
    keys_exact(request, ["schema", "request_id", "parent_execution_id", "profile", "arithmetic", "semantics", "payload"])
    request["schema"] == "ciw.native-interop-request.v1" || throw(ArgumentError("unsupported request schema"))
    identifier(request["request_id"]); identifier(request["parent_execution_id"])
    profile = request["profile"]
    profile in PROFILES || throw(ArgumentError("unsupported profile"))
    request["arithmetic"] == (profile == "affine-d256.v1" ? "exact-d256" : "binary64") || throw(ArgumentError("wrong arithmetic profile"))
    semantics = profile in ["oscillator-tsit5.v1", "control-oscillator.v1"] ? PHYSICAL : GEOMETRIC
    request["semantics"] == semantics || throw(ArgumentError("semantics differ from the declared profile"))
    payload = request["payload"]
    profile == "affine-binary64.v1" && return affine(payload,false)
    profile == "affine-d256.v1" && return affine(payload,true)
    profile == "oscillator-tsit5.v1" && return oscillator(payload,request["request_id"])
    profile == "control-oscillator.v1" && return control(payload)
    quadratic(payload)
end

function main()
    LinearAlgebra.BLAS.set_num_threads(1)
    bytes = read_frame(stdin)
    bytes === nothing && return
    hello = decode(bytes)
    keys_exact(hello,["schema","request_id"])
    hello["schema"] == "ciw.native-interop-handshake-request.v1" || throw(ArgumentError("invalid handshake"))
    identifier(hello["request_id"])
    write_frame(stdout,Dict("schema" => "ciw.native-interop-handshake-response.v1", "request_id" => hello["request_id"],
        "status" => "ok", "identity" => identity(), "profiles" => PROFILES))
    seen = Set{String}()
    while true
        bytes = read_frame(stdin)
        bytes === nothing && return
        request = decode(bytes)
        rid = identifier(get(request,"request_id",nothing))
        parent = identifier(get(request,"parent_execution_id",nothing))
        rid in seen && throw(ArgumentError("duplicate or stale request occurrence"))
        length(seen) < 4096 || throw(ArgumentError("worker occurrence limit reached"))
        push!(seen,rid)
        response = Dict{String,Any}("schema" => "ciw.native-interop-response.v1", "request_id" => rid,
            "parent_execution_id" => parent, "profile" => get(request,"profile","unsupported"))
        try
            data = redirect_stdout(stderr) do
                execute(request)
            end
            response["status"] = "ok"
            response["data"] = data
        catch exception
            message = first(sprint(showerror,exception),2048)
            println(stderr,"native-interop refusal: ",message)
            response["status"] = "refused"
            response["refusal"] = Dict("code" => exception isa ArgumentError ? "INVALID_REQUEST" : "NUMERICAL_FAILURE", "message" => message)
        end
        write_frame(stdout,response)
    end
end
end

if abspath(PROGRAM_FILE) == @__FILE__
    try
        CIWNativeInteropWorker.main()
    catch exception
        println(stderr,"native-interop transport failure: ",first(sprint(showerror,exception),2048))
        exit(2)
    end
end
