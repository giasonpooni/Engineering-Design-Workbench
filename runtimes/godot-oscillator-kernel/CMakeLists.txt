cmake_minimum_required(VERSION 3.20)
project(ciw_oscillator_godot LANGUAGES CXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
    message(FATAL_ERROR "This qualified recipe is Linux x86-64 only")
endif()
foreach(required GODOT_CPP_DIR CIW_KERNEL_DIR CIW_HEADERS_DIR CIW_PROJECT_DIR)
    if(NOT IS_ABSOLUTE "${${required}}")
        message(FATAL_ERROR "Supply absolute ${required}")
    endif()
endforeach()
set(GODOTCPP_BUILD_PROFILE "${CMAKE_CURRENT_SOURCE_DIR}/build_profile.json" CACHE PATH "" FORCE)
set(GODOTCPP_TARGET "template_debug" CACHE STRING "" FORCE)
set(GODOTCPP_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory("${GODOT_CPP_DIR}" "${CMAKE_BINARY_DIR}/godot-cpp")
add_library(ciw_kernel SHARED IMPORTED)
set_target_properties(ciw_kernel PROPERTIES
    IMPORTED_LOCATION "${CIW_KERNEL_DIR}/libciw_oscillator_kernel.so"
    IMPORTED_NO_SONAME TRUE)
add_library(ciw_oscillator_godot SHARED src/extension.cpp)
target_compile_features(ciw_oscillator_godot PRIVATE cxx_std_17)
target_include_directories(ciw_oscillator_godot PRIVATE "${CIW_HEADERS_DIR}")
target_link_libraries(ciw_oscillator_godot PRIVATE godot-cpp ciw_kernel)
target_compile_options(ciw_oscillator_godot PRIVATE -fno-fast-math -ffp-contract=off)
set_target_properties(ciw_oscillator_godot PROPERTIES
    CXX_EXTENSIONS OFF CXX_VISIBILITY_PRESET hidden
    POSITION_INDEPENDENT_CODE ON
    BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "$ORIGIN"
    INSTALL_RPATH_USE_LINK_PATH FALSE
    LIBRARY_OUTPUT_DIRECTORY "${CIW_PROJECT_DIR}/bin")
