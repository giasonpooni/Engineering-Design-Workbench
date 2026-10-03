# Bounded source exporter, NOT a general Julia compiler. No package installation.
# The model is parsed and checked before any evaluation. Only Float64 arithmetic
# on four scalar arguments is supported. No rewriting/reassociation is performed.
using SHA

const ARGUMENTS = [:q, :v, :gamma, :omega]
const SIGNATURE = Expr(:call, :oscillator_rhs, ARGUMENTS...)

function cexpr(node, depth=0, budget=Ref(128))
    budget[] -= 1
    depth <= 16 && budget[] >= 0 || error("expression exceeds profile limits")
    if node isa Symbol
        node in ARGUMENTS || error("unsupported symbol: $node")
        return String(node)
    elseif node isa Float64
        isfinite(node) && abs(node) <= 1e6 || error("literal outside profile")
        return repr(node)
    elseif node isa Expr && node.head == :call
        op, args = node.args[1], node.args[2:end]
        op in (:+, :-, :*) || error("unsupported operator: $op")
        if op == :- && length(args) == 1
            return "(-" * cexpr(args[1], depth + 1, budget) * ")"
        end
        length(args) >= 2 || error("operator arity is unsupported")
        op == :- && length(args) != 2 && error("subtraction must be binary")
        parts = [cexpr(x, depth + 1, budget) for x in args]
        return foldl((a,b) -> "(" * a * " " * String(op) * " " * b * ")", parts)
    end
    error("unsupported syntax or non-Float64 literal")
end

function checked_definition(text)
    ncodeunits(text) <= 8192 || error("source exceeds 8192 bytes")
    tree = Meta.parseall(text)
    tree isa Expr && tree.head == :toplevel || error("expected top-level definition")
    nodes = filter(x -> !(x isa LineNumberNode), tree.args)
    length(nodes) == 1 || error("exactly one definition is permitted")
    def = only(nodes)
    def isa Expr && def.head == :(=) && length(def.args) == 2 || error("expected short function")
    def.args[1] == SIGNATURE || error("expected oscillator_rhs(q, v, gamma, omega)")
    rhs = def.args[2]
    # Julia may wrap a short-function RHS in a line-numbered singleton block.
    while rhs isa Expr && rhs.head == :block
        body = filter(x -> !(x isa LineNumberNode), rhs.args)
        length(body) == 1 || error("statement blocks are not supported")
        rhs = only(body)
    end
    rhs isa Expr && rhs.head == :tuple && length(rhs.args) == 2 || error("expected two outputs")
    budget = Ref(128)
    expressions = [cexpr(x, 0, budget) for x in rhs.args]
    return def, expressions
end

function export_kernel(source, destination)
    raw = read(source)
    _, expressions = checked_definition(String(copy(raw)))
    template = read(joinpath(@__DIR__, "abi.c.in"), String)
    emitted = replace(template, "@RHS_Q@" => expressions[1], "@RHS_V@" => expressions[2],
                      "@SOURCE_SHA256@" => bytes2hex(sha256(raw)))
    occursin(r"@[A-Z_0-9]+@", emitted) && error("unresolved template token")
    ispath(destination) && error("refusing to overwrite generated source")
    write(destination, emitted)
end

function reference(source, inputs, outputs)
    def, _ = checked_definition(read(source, String))
    # Only the validated arithmetic definition is evaluated, never arbitrary source.
    mod = Module(gensym(:CIWOscillatorReference))
    Core.eval(mod, def)
    function_object = getfield(mod, :oscillator_rhs)
    filesize(inputs) <= 1024^2 || error("reference input exceeds byte limit")
    rows = readlines(inputs)
    1 <= length(rows) <= 4096 || error("reference input exceeds row limit")
    values = NTuple{2,Float64}[]
    for row in rows
        fields = split(row, '\t')
        length(fields) == 4 || error("expected q, v, gamma, omega")
        q, v, gamma, omega = parse.(Float64, fields)
        all(isfinite, (q,v,gamma,omega)) || error("nonfinite input")
        abs(q) <= 1e6 && abs(v) <= 1e6 && eps(Float64) <= omega <= 20.0 &&
            0.0 <= gamma <= 0.5*omega || error("input outside profile")
        value = Base.invokelatest(function_object, q, v, gamma, omega)
        all(isfinite, value) || error("nonfinite reference output")
        push!(values, value)
    end
    ispath(outputs) && error("refusing to overwrite reference output")
    open(outputs, "w") do io
        for value in values
            println(io, repr(value[1]), '\t', repr(value[2]))
        end
    end
end

function selftest()
    accepted = "oscillator_rhs(q, v, gamma, omega) = (v, ((-2.0 * gamma) * v) - ((omega * omega) * q))"
    _, rhs = checked_definition(accepted)
    rhs[1] == "v" || error("first output changed")
    for bad in (
        accepted * "; println(123)",
        "oscillator_rhs(q, v, gamma, omega) = (v, sin(q))",
        "oscillator_rhs(q, v, gamma, omega) = (v, q^2)",
        "oscillator_rhs(q, v, gamma, omega) = (v, unknown)",
        "oscillator_rhs(q, v, gamma, omega) = (v, true)",
        "oscillator_rhs(q, v, gamma, omega) = (v, 2 * q)",
        "oscillator_rhs(q, v, gamma, omega) = (v, eval(q))",
        "oscillator_rhs(q, v, gamma, omega) = (v, @fastmath q + v)",
        "oscillator_rhs(q, v, gamma, omega) = (v, begin q; v end)",
        "oscillator_rhs(q, v, gamma, omega) = (v, q[1])",
    )
        refused = false
        try
            checked_definition(bad)
        catch
            refused = true
        end
        refused || error("unsupported expression was accepted")
    end
    println("exporter self-test: passed")
end

if abspath(PROGRAM_FILE) == @__FILE__
    if length(ARGS) == 1 && ARGS[1] == "selftest"
        selftest()
    elseif length(ARGS) == 3 && ARGS[1] == "export"
        export_kernel(ARGS[2], ARGS[3])
    elseif length(ARGS) == 4 && ARGS[1] == "reference"
        reference(ARGS[2], ARGS[3], ARGS[4])
    else
        error("usage: export.jl selftest | export SOURCE DEST.c | reference SOURCE INPUT.tsv OUTPUT.tsv")
    end
end
