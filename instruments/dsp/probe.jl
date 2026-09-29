# Actual Julia caller plus an independent 256-bit direct-convolution reference.
include(joinpath(ARGS[1], "scr_dsp.jl"))
using .ScrDsp, Printf
lib = ScrDsp.Library(ARGS[2]; expected_sha256=ARGS[3])
setprecision(BigFloat,256) do
    for line in eachline(ARGS[4])
        fields=split(line); isempty(fields) && continue
        k,n,s=parse.(Int,fields[1:3])
        values=parse.(Float64,fields[4:end])
        length(values)==k+k-1+n || error("Corpus length")
        b=values[1:k]; h=values[k+1:2k-1]; x=values[2k:end]
        y,z=ScrDsp.fir(lib,b,x,h)
        left,zl=ScrDsp.fir(lib,b,x[1:s],h)
        right,zr=ScrDsp.fir(lib,b,x[s+1:end],zl)
        y==vcat(left,right) && z==zr || error("Chunk continuity")
        extended=BigFloat.(vcat(h,x)); coefficients=BigFloat.(b)
        reference=[Float64(sum(coefficients[j]*extended[k+i-j] for j in 1:k)) for i in 1:n]
        all(abs(y[i]-reference[i]) <= 1e-12+1e-12*abs(reference[i]) for i in 1:n) || error("Independent Julia reference")
        for v in vcat(reference,z); @printf("%.17g ",v); end
        println()
    end
end
close(lib)
