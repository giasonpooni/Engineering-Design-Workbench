#pragma once
#include "rust/cxx.h"
#include <cstdint>
namespace scr {
struct FloatResponse;
struct ExactResponse;
struct ForceResponse;
FloatResponse affine_f64(std::uint32_t rows, std::uint32_t columns, rust::Slice<const double> a, rust::Slice<const double> b, rust::Slice<const double> x, rust::Slice<const double> delta);
ExactResponse affine_d256(std::uint32_t rows, std::uint32_t columns, rust::Slice<const std::int64_t> a, rust::Slice<const std::int64_t> b, rust::Slice<const std::int64_t> x, rust::Slice<const std::int64_t> delta);
ForceResponse oscillator_force(double mass, double omega, double gamma, rust::Slice<const double> q, rust::Slice<const double> v);
}
