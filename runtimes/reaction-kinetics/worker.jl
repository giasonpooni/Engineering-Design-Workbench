#!/usr/bin/env julia
"""Bounded, framed Catalyst benchmark; requests contain data, never Julia code."""
module CIWReactionCatalystWorker

redirect_stdout(stderr) do
    @eval using Catalyst, OrdinaryDiffEqTsit5, SciMLBase, JSON3
    @eval using SymbolicIndexingInterface, SHA, LinearAlgebra
end

const PROFILE = "reaction-a-to-b.v1"
const MODEL = "closed-isothermal-a-to-b.v1"
const MAX_FRAME = 1024 * 1024
const MAX_REQUESTS = 256
const SEMANTICS = Dict("layout" => "time-major", "concentration_unit" => "mol/m^3",
    "production_rate_unit" => "mol/m^3/s", "time_unit" => "s", "temperature_unit" => "K",
    "volume_unit" => "m^3", "frame" => "homogeneous-control-volume", "clock" => "declared-simulation-time")

# These are abstract, identical-composition model species, not a model of real
# hydrogen chemistry. Prescribed temperature and fixed volume are parameters,
# not additional dynamic states. Catalyst evaluates the concentration ODE;
# the equal thermo closure is retained for comparison with the Cantera profile.
const THERMO_CLOSURE = (composition=(H=1,), charge=0, phase="gas",
    T0_K=300.0, h0_J_kmol=0.0, s0_J_kmol_K=0.0, cp0_J_kmol_K=20786.156545383,
    minimum_K=200.0, maximum_K=1000.0)

const NETWORK = @reaction_network begin
    k, A --> B
end

function keys_exact(value, expected)
    value isa AbstractDict && Set(keys(value)) == Set(expected) ||
        throw(ArgumentError("fields differ from the fixed request contract"))
end

function number(value, lo, hi)
    value isa Real && !(value isa Bool) && isfinite(value) && lo <= value <= hi ||
        throw(ArgumentError("number outside finite declared bounds"))
    Float64(value)
end

function identifier(value)
    value isa String && occursin(r"\A[A-Za-z0-9_.:/-]{1,160}\z", value) ||
        throw(ArgumentError("invalid request or execution identifier"))
    value
end

function validate(request)
    keys_exact(request, ["schema", "request_id", "parent_execution_id", "profile", "arithmetic", "semantics", "payload"])
    request["schema"] == "ciw.native-interop-request.v1" && request["profile"] == PROFILE &&
        request["arithmetic"] == "binary64" || throw(ArgumentError("unsupported reaction profile"))
    identifier(request["request_id"])
    identifier(request["parent_execution_id"])
    request["semantics"] == SEMANTICS || throw(ArgumentError("reaction units, frame or clock differ"))
    p = request["payload"]
    keys_exact(p, ["model", "species_order", "initial_concentration_mol_m3", "rate_constant_s_inv",
        "temperature_k", "volume_m3", "time_s", "solver"])
    p["model"] == MODEL || throw(ArgumentError("unsupported chemical mechanism"))
    p["species_order"] in (["A", "B"], ["B", "A"]) || throw(ArgumentError("species order must name A and B exactly once"))
    initial = p["initial_concentration_mol_m3"]
    initial isa AbstractVector && length(initial) == 2 || throw(ArgumentError("exactly two concentrations required"))
    concentration = [number(v, 0, 1000) for v in initial]
    1e-6 <= sum(concentration) <= 1000 || throw(ArgumentError("total concentration outside profile"))
    rate = number(p["rate_constant_s_inv"], 0, 10)
    temperature = number(p["temperature_k"], 250, 500)
    THERMO_CLOSURE.minimum_K <= temperature <= THERMO_CLOSURE.maximum_K ||
        throw(ArgumentError("temperature outside code-owned thermo closure"))
    number(p["volume_m3"], 1e-6, 1)
    times = p["time_s"]
    times isa AbstractVector && 2 <= length(times) <= 128 || throw(ArgumentError("time grid exceeds profile"))
    previous = -1.0
    for value in times
        current = number(value, 0, 100)
        current > previous || throw(ArgumentError("time grid must increase strictly"))
        previous = current
    end
    times[1] == 0 && rate * times[end] <= 30 || throw(ArgumentError("time span outside reaction profile"))
    solver = p["solver"]
    keys_exact(solver, ["reltol", "abstol_mol_m3", "max_steps"])
    number(solver["reltol"], 1e-9, 1e-9)
    number(solver["abstol_mol_m3"], 1e-11, 1e-11)
    steps = solver["max_steps"]
    steps isa Integer && !(steps isa Bool) && 1 <= steps <= 100000 ||
        throw(ArgumentError("max_steps must be an integer in 1..100000"))
    p
end

function execute(request)
    p = validate(request)
    order = String.(p["species_order"])
    concentrations = Float64.(p["initial_concentration_mol_m3"])
    a0 = concentrations[findfirst(==("A"), order)]
    b0 = concentrations[findfirst(==("B"), order)]
    times = Float64.(p["time_s"])
    rate = Float64(p["rate_constant_s_inv"])
    # Catalyst generates the executed RHS; the closed-form analytic solution
    # is deliberately absent from this worker and lives in independent tests.
    problem = ODEProblem(NETWORK, [:A => a0, :B => b0], (times[1], times[end]), [:k => rate];
                         combinatoric_ratelaws=false)
    ia = SymbolicIndexingInterface.variable_index(problem, NETWORK.A)
    ib = SymbolicIndexingInterface.variable_index(problem, NETWORK.B)
    ia isa Integer && ib isa Integer && ia != ib || error("Catalyst species indexing unavailable")
    indices = order == ["A", "B"] ? [ia, ib] : [ib, ia]
    solution = solve(problem, Tsit5(); reltol=1e-9, abstol=1e-11,
        maxiters=Int(p["solver"]["max_steps"]), saveat=times, dense=false, save_everystep=false)
    solution.retcode == ReturnCode.Success || error("Catalyst Tsit5 returned $(solution.retcode)")
    length(solution.u) == length(times) && solution.t == times || error("solver did not cover the requested grid")
    output = Vector{Vector{Float64}}()
    production = Vector{Vector{Float64}}()
    for (state, time) in zip(solution.u, times)
        derivative = similar(state)
        problem.f(derivative, state, problem.p, time)
        # Preserve raw numerical concentrations, including tiny negative values.
        push!(output, Float64[state[i] for i in indices])
        push!(production, Float64[derivative[i] for i in indices])
    end
    all(row -> all(isfinite, row), output) && all(row -> all(isfinite, row), production) ||
        error("nonfinite reaction output")
    source = read(@__FILE__)
    Dict("model" => MODEL, "species_order" => order, "time_s" => times,
        "concentration_mol_m3" => output, "production_rate_mol_m3_s" => production,
        "mechanism" => Dict("format" => "catalyst-code-v1", "bytes_hex" => bytes2hex(source),
                            "sha256" => "sha256:" * bytes2hex(sha256(source))),
        "solver" => Dict("algorithm" => "Catalyst.Tsit5", "retcode" => "Success", "reltol" => 1e-9,
                         "abstol_mol_m3" => 1e-11, "max_steps" => p["solver"]["max_steps"]))
end

function identity()
    hashfile(name) = "sha256:" * bytes2hex(sha256(read(joinpath(@__DIR__, name))))
    Dict("schema" => "ciw.reaction-catalyst-identity.v1", "julia_version" => string(VERSION),
        "platform" => string(Sys.MACHINE), "threads" => Threads.nthreads(),
        "worker_sha256" => hashfile("worker.jl"), "project_sha256" => hashfile("Project.toml"),
        "manifest_sha256" => hashfile("Manifest.toml"),
        "packages" => Dict("Catalyst" => string(pkgversion(Catalyst)),
            "OrdinaryDiffEqTsit5" => string(pkgversion(OrdinaryDiffEqTsit5)),
            "SciMLBase" => string(pkgversion(SciMLBase)), "JSON3" => string(pkgversion(JSON3)),
            "SymbolicIndexingInterface" => string(pkgversion(SymbolicIndexingInterface))))
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

function plain(value)
    if value isa JSON3.Object
        result = Dict{String,Any}()
        for (key, child) in value
            name = String(key)
            haskey(result, name) && throw(ArgumentError("duplicate JSON key"))
            result[name] = plain(child)
        end
        result
    elseif value isa JSON3.Array
        [plain(child) for child in value]
    else
        value
    end
end

function decode(bytes)
    isvalid(String, bytes) || throw(ArgumentError("request must be UTF-8"))
    # Enforce nesting before the general JSON parser allocates recursive data.
    depth, quoted, escaped = 0, false, false
    started, complete = false, false
    for byte in bytes
        whitespace = byte in (0x20, 0x09, 0x0a, 0x0d)
        if !started
            whitespace && continue
            byte == UInt8('{') || throw(ArgumentError("request must be a JSON object"))
            started = true
        elseif complete
            whitespace || throw(ArgumentError("trailing content after JSON object"))
            continue
        end
        if quoted
            if escaped
                escaped = false
            elseif byte == UInt8('\\')
                escaped = true
            elseif byte == UInt8('"')
                quoted = false
            end
        elseif byte == UInt8('"')
            quoted = true
        elseif byte in (UInt8('{'), UInt8('['))
            depth += 1
            depth <= 16 || throw(ArgumentError("JSON nesting exceeds bounds"))
        elseif byte in (UInt8('}'), UInt8(']'))
            depth -= 1
            depth == 0 && (complete = true)
        end
    end
    complete && !quoted && depth == 0 || throw(ArgumentError("incomplete JSON object"))
    # A byte vector avoids JSON3's string overload interpreting a local path.
    plain(JSON3.read(bytes))
end

function main()
    LinearAlgebra.BLAS.set_num_threads(1)
    bytes = read_frame(stdin)
    bytes === nothing && return
    hello = decode(bytes)
    keys_exact(hello, ["schema", "request_id"])
    hello["schema"] == "ciw.native-interop-handshake-request.v1" || throw(ArgumentError("invalid handshake"))
    identifier(hello["request_id"])
    write_frame(stdout, Dict("schema" => "ciw.native-interop-handshake-response.v1", "status" => "ok",
        "request_id" => hello["request_id"], "identity" => identity(), "profiles" => [PROFILE]))
    seen = Set{String}()
    while true
        bytes = read_frame(stdin)
        bytes === nothing && return
        request = decode(bytes)
        request isa AbstractDict || throw(ArgumentError("request must be an object"))
        rid = identifier(get(request, "request_id", nothing))
        parent = identifier(get(request, "parent_execution_id", nothing))
        rid in seen && throw(ArgumentError("duplicate or stale request occurrence"))
        length(seen) < MAX_REQUESTS || throw(ArgumentError("worker occurrence limit reached"))
        push!(seen, rid)
        response = Dict{String,Any}("schema" => "ciw.native-interop-response.v1", "request_id" => rid,
            "parent_execution_id" => parent, "profile" => get(request, "profile", "unsupported"))
        try
            response["data"] = redirect_stdout(stderr) do
                execute(request)
            end
            response["status"] = "ok"
        catch exception
            message = first(sprint(showerror, exception), 2048)
            println(stderr, "reaction-catalyst refusal: ", message)
            response["status"] = "refused"
            response["refusal"] = Dict("code" => exception isa ArgumentError ? "INVALID_REQUEST" : "NUMERICAL_FAILURE",
                                        "message" => message)
        end
        write_frame(stdout, response)
    end
end
end

if abspath(PROGRAM_FILE) == @__FILE__
    try
        CIWReactionCatalystWorker.main()
    catch exception
        println(stderr, "reaction-catalyst transport failure: ", first(sprint(showerror, exception), 2048))
        exit(2)
    end
end
