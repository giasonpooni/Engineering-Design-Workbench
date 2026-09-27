#!/usr/bin/env julia
"""Fixed scalar-square remainder enclosure; requests contain data, never code."""
module CIWIntervalWorker

redirect_stdout(stderr) do
    @eval using IntervalArithmetic, JSON3, SHA
end
# Configuration is code-owned and cannot be changed by a request. Configure at
# module initialization so redefined interval methods are visible to execution.
redirect_stdout(stderr) do
    IntervalArithmetic.configure(; numtype=Float64, flavor=:set_based,
        rounding=:correct, power=:slow, matmul=:slow, nthreads=1)
end

const PROFILE = "scalar-square-interval.v1"
const MODEL = "scalar-square.v1"
const MAX_FRAME = 1024 * 1024
const MAX_REQUESTS = 256
const SEMANTICS = Dict("layout" => "scalar", "input_unit" => "1", "output_unit" => "1",
    "frame" => "dimensionless-cartesian", "clock" => "not_applicable")
const CONFIGURATION = Dict("input_encoding" => "reduced-rational",
    "endpoint_encoding" => "ieee754-binary64-hex", "rounding" => "correct", "power" => "slow",
    "decoration" => "com", "guaranteed" => true, "covariance_status" => "not_applicable",
    "calibration_status" => "not_applicable")

function keys_exact(value, expected)
    value isa AbstractDict && Set(keys(value)) == Set(expected) ||
        throw(ArgumentError("fields differ from the fixed request contract"))
end

function identifier(value)
    value isa String && occursin(r"\A[A-Za-z0-9_.:/-]{1,160}\z", value) ||
        throw(ArgumentError("invalid request or execution identifier"))
    value
end

function rational(value)
    keys_exact(value, ["numerator", "denominator"])
    n, d = value["numerator"], value["denominator"]
    n isa Integer && !(n isa Bool) && d isa Integer && !(d isa Bool) ||
        throw(ArgumentError("rational components must be integers"))
    -1000000 <= n <= 1000000 && 1 <= d <= 1000000 && gcd(n, d) == 1 ||
        throw(ArgumentError("rational must be reduced with bounded numerator and positive denominator"))
    BigInt(n) // BigInt(d)
end

function validate(request)
    keys_exact(request, ["schema", "request_id", "parent_execution_id", "profile", "arithmetic", "semantics", "payload"])
    request["schema"] == "ciw.native-interop-request.v1" && request["profile"] == PROFILE &&
        request["arithmetic"] == "outward-binary64" || throw(ArgumentError("unsupported interval profile"))
    identifier(request["request_id"])
    identifier(request["parent_execution_id"])
    request["semantics"] == SEMANTICS || throw(ArgumentError("interval units, frame or clock differ"))
    p = request["payload"]
    keys_exact(p, ["model", "x", "variation_lower", "variation_upper", "error_limit"])
    p["model"] == MODEL || throw(ArgumentError("unsupported scalar model"))
    x, lo, hi, limit = (rational(p[k]) for k in ("x", "variation_lower", "variation_upper", "error_limit"))
    -100 <= x <= 100 && -200 <= lo <= hi <= 200 &&
        -100 <= x + lo <= x + hi <= 100 && 0 <= limit <= 40000 ||
        throw(ArgumentError("rational source outside the declared domain"))
    x, lo, hi, limit
end

function execute(request)
    _, lo, hi, limit = validate(request)
    # Exact rational sources are passed to the outward constructor. Converting
    # them to Float64 first would silently change the specified mathematical box.
    u = interval(Float64, lo, hi)
    epsilon = interval(Float64, limit)
    enclosure = u^2 - epsilon
    !isnai(enclosure) && !isempty_interval(enclosure) &&
        decoration(enclosure) == com && isguaranteed(enclosure) ||
        error("interval result lost common decoration or guarantee")
    lower, upper = inf(enclosure), sup(enclosure)
    isfinite(lower) && isfinite(upper) && lower <= upper || error("invalid finite interval result")
    conclusion = upper <= 0 ? "holds_throughout" : lower > 0 ? "fails_throughout" : "inconclusive"
    encode(value) = string(reinterpret(UInt64, value); base=16, pad=16)
    Dict("model" => MODEL, "expression" => "u^2-error_limit",
        "enclosure" => Dict("lower_hex" => encode(lower), "upper_hex" => encode(upper),
            "decoration" => string(decoration(enclosure)), "guaranteed" => isguaranteed(enclosure)),
        "requirement" => conclusion, "configuration" => copy(CONFIGURATION))
end

function identity()
    hashfile(name) = "sha256:" * bytes2hex(sha256(read(normpath(joinpath(@__DIR__, name)))))
    Dict("schema" => "ciw.interval-julia-identity.v1", "julia_version" => string(VERSION),
        "platform" => string(Sys.MACHINE), "threads" => Threads.nthreads(),
        "worker_sha256" => hashfile("worker.jl"), "project_sha256" => hashfile("Project.toml"),
        "manifest_sha256" => hashfile("Manifest.toml"),
        "packages" => Dict("IntervalArithmetic" => string(pkgversion(IntervalArithmetic)),
            "JSON3" => string(pkgversion(JSON3))))
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

function validate_integer_encoding(bytes)
    # JSON3 normalizes numeric tokens such as 1.0 and 1e0 to Int and accepts
    # non-JSON spellings such as +1. Check complete unquoted primitive tokens
    # before accepting the parsed rational components. Strings are not numbers.
    unquoted = UInt8[]
    quoted, escaped = false, false
    for byte in bytes
        if quoted
            if escaped
                escaped = false
            elseif byte == UInt8('\\')
                escaped = true
            elseif byte == UInt8('"')
                quoted = false
                push!(unquoted, 0x20)
            end
        elseif byte == UInt8('"')
            quoted = true
            push!(unquoted, 0x20)
        else
            push!(unquoted, byte)
        end
    end
    for token in eachmatch(r"[^{}\[\],:\x20\t\r\n]+", String(unquoted))
        token.match in ("true", "false", "null") && continue
        occursin(r"\A-?(0|[1-9][0-9]*)\z", token.match) ||
            throw(ArgumentError("rational components require JSON integer tokens"))
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
                validate_integer_encoding(bytes)
                execute(request)
            end
            response["status"] = "ok"
        catch exception
            message = first(sprint(showerror, exception), 2048)
            println(stderr, "interval refusal: ", message)
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
        CIWIntervalWorker.main()
    catch exception
        println(stderr, "interval transport failure: ", first(sprint(showerror, exception), 2048))
        exit(2)
    end
end
