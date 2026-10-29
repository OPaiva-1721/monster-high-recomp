/* The NDK's clang ships bionic's <stdatomic.h>, which needs <sys/cdefs.h>.
 * On a Windows host build route to the MSVC runtime's C11/C++ versions. */
#pragma once
#ifdef __cplusplus
#include <__msvc_cxx_stdatomic.hpp>
#else
#include <vcruntime_c11_stdatomic.h>
#endif
