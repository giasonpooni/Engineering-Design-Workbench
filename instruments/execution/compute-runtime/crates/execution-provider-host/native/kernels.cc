#include "scr-provider-host/src/ffi.rs.h"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace scr {
namespace {
void shape(std::uint32_t m, std::uint32_t n, std::size_t a, std::size_t b, std::size_t x, std::size_t d) {
  if (m < 1 || m > 8 || n < 1 || n > 8 || a != std::size_t(m)*n || b != m || x != n || d != n)
    throw std::invalid_argument("invalid row-major affine dimensions");
}
void finite(double v, double bound) { if (!std::isfinite(v) || std::abs(v)>bound) throw std::invalid_argument("nonfinite or out-of-domain native input"); }
std::int64_t add(std::int64_t a, std::int64_t b) {
  if ((b>0 && a>std::numeric_limits<std::int64_t>::max()-b) || (b<0 && a<std::numeric_limits<std::int64_t>::min()-b)) throw std::overflow_error("integer addition overflow");
  return a+b;
}
std::int64_t mul(std::int64_t a, std::int64_t b) {
  // Profile operands and intermediates are bounded; this guard is independent
  // of caller validation and precedes the multiplication itself.
  if (a < -1073741824LL || a > 1073741824LL || b < -1073741824LL || b > 1073741824LL) throw std::overflow_error("integer product operand limit");
  return a*b; // absolute product <= 2^60, within signed int64.
}
}
FloatResponse affine_f64(std::uint32_t m, std::uint32_t n, rust::Slice<const double> a, rust::Slice<const double> b, rust::Slice<const double> x, rust::Slice<const double> d) {
  shape(m,n,a.size(),b.size(),x.size(),d.size());
  for (double z:a) finite(z,1e6); for (double z:b) finite(z,1e6); for (double z:x) finite(z,1e6); for (double z:d) finite(z,1e6);
  FloatResponse out;
  for (std::uint32_t i=0;i<m;++i) {
    double base=b[i], change=0, model=b[i];
    for (std::uint32_t j=0;j<n;++j) {
      const double coefficient=a[std::size_t(i)*n+j], contribution=coefficient*d[j];
      base += coefficient*x[j]; change += contribution; model += coefficient*(x[j]+d[j]);
      out.contributions.push_back(contribution);
    }
    const double prediction=base+change;
    finite(base,1e15); finite(change,1e15); finite(model,1e15); finite(prediction,1e15);
    out.baseline_output.push_back(base); out.predicted_delta.push_back(change);
    out.predicted_output.push_back(prediction); out.model_output.push_back(model); out.residual.push_back(model-prediction);
  }
  return out;
}
ExactResponse affine_d256(std::uint32_t m, std::uint32_t n, rust::Slice<const std::int64_t> a, rust::Slice<const std::int64_t> b, rust::Slice<const std::int64_t> x, rust::Slice<const std::int64_t> d) {
  shape(m,n,a.size(),b.size(),x.size(),d.size());
  for (auto values:{a,b,x,d}) for (auto z:values) if(z < -4096 || z > 4096) throw std::invalid_argument("D256 numerator outside [-4096,4096]");
  ExactResponse out;
  for (std::uint32_t i=0;i<m;++i) {
    std::int64_t base=mul(b[i],256), change=0, model=base;
    for (std::uint32_t j=0;j<n;++j) {
      auto coefficient=a[std::size_t(i)*n+j], contribution=mul(coefficient,d[j]);
      base=add(base,mul(coefficient,x[j])); change=add(change,contribution);
      model=add(model,mul(coefficient,add(x[j],d[j]))); out.contributions.push_back(contribution);
    }
    auto prediction=add(base,change);
    out.baseline_output.push_back(base); out.predicted_delta.push_back(change);
    out.predicted_output.push_back(prediction); out.model_output.push_back(model); out.residual.push_back(add(model,-prediction));
  }
  return out;
}
ForceResponse oscillator_force(double mass, double omega, double gamma, rust::Slice<const double> q, rust::Slice<const double> v) {
  finite(mass,100); finite(omega,20); finite(gamma,10);
  if (mass<=1e-12 || omega<=1e-12 || gamma<0 || gamma>omega/2 || q.empty() || q.size()>4096 || q.size()!=v.size()) throw std::invalid_argument("invalid oscillator domain or sample shape");
  ForceResponse out; out.stiffness_n_m=mass*omega*omega; out.damping_n_s_m=2*mass*gamma;
  for (std::size_t i=0;i<q.size();++i) {
    finite(q[i],1000); finite(v[i],1000);
    const auto restoring=-out.stiffness_n_m*q[i], damping=-out.damping_n_s_m*v[i], net=restoring+damping;
    const auto potential=0.5*out.stiffness_n_m*q[i]*q[i], kinetic=0.5*mass*v[i]*v[i];
    out.restoring_force_n.push_back(restoring); out.damping_force_n.push_back(damping); out.net_force_n.push_back(net);
    out.acceleration_m_s2.push_back(net/mass); out.potential_energy_j.push_back(potential); out.kinetic_energy_j.push_back(kinetic); out.energy_j.push_back(potential+kinetic);
  }
  return out;
}
}
