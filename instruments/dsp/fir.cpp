// Causal FIR provider. Mathematics belongs to SCR, not NET orchestration.
// Caller owns all buffers and the history. No retained pointers or allocations.
#include "scr_dsp.h"
#include <array>
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <limits>

static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559);
extern "C" uint32_t scr_dsp_abi_version(void) { return SCR_DSP_ABI_VERSION; }
extern "C" const char* scr_dsp_contract_sha256(void) { return SCR_DSP_CONTRACT_SHA256; }

// Status: 0 success; 1 null; 2 lengths; 3 nonfinite input; 4 nonfinite result;
// 5 output overlap/address range; 6 unsupported floating-point rounding mode.
extern "C" int32_t scr_dsp_fir_v1(const double* taps, size_t taps_len,
    const double* samples, size_t samples_len, const double* history, size_t history_len,
    double* output, size_t output_len, double* next_history, size_t next_history_len) {
    if (taps_len < 1 || taps_len > 64 || samples_len < 1 || samples_len > 4096 ||
        history_len != taps_len - 1 || output_len != samples_len || next_history_len != history_len) return 2;
    if (!taps || !samples || !output || (history_len && (!history || !next_history))) return 1;
    if (std::fegetround() != FE_TONEAREST) return 6;
    const auto a = reinterpret_cast<uintptr_t>(output), b = reinterpret_cast<uintptr_t>(next_history);
    const auto an = output_len * sizeof(double), bn = next_history_len * sizeof(double);
    if (a > UINTPTR_MAX - an || b > UINTPTR_MAX - bn || (bn && a < b + bn && b < a + an)) return 5;
    for (size_t i=0; i<taps_len; ++i) if (!std::isfinite(taps[i])) return 3;
    for (size_t i=0; i<samples_len; ++i) if (!std::isfinite(samples[i])) return 3;
    for (size_t i=0; i<history_len; ++i) if (!std::isfinite(history[i])) return 3;
    std::array<double,4096> candidate{};
    std::array<double,63> retained{};
    for (size_t n=0; n<samples_len; ++n) {
        double y=0.0;
        for (size_t k=0; k<taps_len; ++k) {
            const double x = k<=n ? samples[n-k] : history[history_len+n-k];
            y += taps[k]*x;
        }
        if (!std::isfinite(y)) return 4;
        candidate[n]=y;
    }
    for (size_t i=0; i<history_len; ++i) {
        const size_t index=samples_len+i;
        retained[i] = index<history_len ? history[index] : samples[index-history_len];
    }
    // Commit only after all inputs are consumed and every result validated.
    // Output/input aliasing is supported; the two output ranges must be disjoint.
    for (size_t i=0; i<output_len; ++i) output[i]=candidate[i];
    for (size_t i=0; i<next_history_len; ++i) next_history[i]=retained[i];
    return 0;
}
