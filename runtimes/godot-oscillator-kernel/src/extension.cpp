#include "oscillator_cpp.hpp"
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_float64_array.hpp>
#include <godot_cpp/variant/string.hpp>

namespace godot {
// Stateless mathematical helper. No SceneTree/physics/NET session authority.
class CIWOscillatorKernel : public RefCounted {
    GDCLASS(CIWOscillatorKernel, RefCounted)
    ciw::OscillatorKernel kernel_;
protected:
    static void _bind_methods() {
        ClassDB::bind_method(D_METHOD("bind_source", "expected_sha256"), &CIWOscillatorKernel::bind_source);
        ClassDB::bind_method(D_METHOD("rhs", "state", "parameters"), &CIWOscillatorKernel::rhs);
    }
public:
    int64_t bind_source(const String& source) {
        const CharString bytes = source.utf8();
        return kernel_.bind_source(std::string_view(bytes.get_data(), bytes.length()));
    }
    Dictionary rhs(const PackedFloat64Array& state, const PackedFloat64Array& parameters) const {
        Dictionary output;
        PackedFloat64Array derivative;
        int32_t status = 2;
        if (state.size() == 2 && parameters.size() == 2) {
            const auto result = kernel_.rhs({state[0],state[1]}, {parameters[0],parameters[1]});
            status = result.status;
            if (status == 0) {
                derivative.resize(2);
                derivative.set(0,result.derivative[0]);
                derivative.set(1,result.derivative[1]);
            }
        }
        output["status"] = status;
        output["derivative"] = derivative; // Empty on failure, never plausible zero output.
        return output;
    }
};
static void initialize(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE) ClassDB::register_class<CIWOscillatorKernel>();
}
static void uninitialize(ModuleInitializationLevel) {}
}
extern "C" {
GDExtensionBool GDE_EXPORT ciw_oscillator_library_init(GDExtensionInterfaceGetProcAddress get_proc,
        GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    godot::GDExtensionBinding::InitObject init(get_proc,library,initialization);
    init.register_initializer(godot::initialize);
    init.register_terminator(godot::uninitialize);
    init.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}
}
