// Checked C++17 consumer of the existing C library, not another RHS implementation.
#ifndef CIW_OSCILLATOR_CPP_HPP
#define CIW_OSCILLATOR_CPP_HPP
#include "oscillator_abi.h"
#include <array>
#include <string_view>

namespace ciw {
struct RhsResult {
    int32_t status = 7; // 7: wrapper unbound or source/ABI mismatch.
    std::array<double, 2> derivative{}; // Valid only when status == 0.
};

class OscillatorKernel final {
    bool bound_ = false;
public:
    // The linked library must be trusted before process startup. The host checks
    // its binary digest; this method additionally checks the ABI and source pin.
    int32_t bind_source(std::string_view expected) noexcept {
        bound_ = false; // A failed rebind must not leave an old binding usable.
        if (expected.size() != 64) return 7;
        for (char ch : expected) {
            if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) return 7;
        }
        if (ciw_oscillator_abi_v1() != 1) return 7;
        const char *actual = ciw_oscillator_source_sha256_v1();
        if (!actual) return 7;
        for (size_t i = 0; i < 64; ++i) {
            if (actual[i] == '\0' || actual[i] != expected[i]) return 7;
        }
        if (actual[64] != '\0') return 7;
        bound_ = true;
        return 0;
    }

    RhsResult rhs(const std::array<double, 2>& state,
                  const std::array<double, 2>& parameters) const noexcept {
        RhsResult result;
        if (!bound_) return result;
        result.status = ciw_oscillator_rhs_v1(state.data(), state.size(),
            parameters.data(), parameters.size(), result.derivative.data(), result.derivative.size());
        return result;
    }
};
}
#endif
