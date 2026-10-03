/* Existing oscillator ABI v1. This header contains declarations, not equations. */
#ifndef CIW_OSCILLATOR_ABI_H
#define CIW_OSCILLATOR_ABI_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t ciw_oscillator_abi_v1(void);
const char *ciw_oscillator_source_sha256_v1(void);
int32_t ciw_oscillator_rhs_v1(const double *state, size_t state_len,
                            const double *parameters, size_t parameters_len,
                            double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
