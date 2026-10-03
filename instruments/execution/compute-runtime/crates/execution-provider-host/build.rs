use std::{env, fs, path::PathBuf, process::Command};

fn main() {
    let mut build = cxx_build::bridge("src/ffi.rs");
    build
        .file("native/kernels.cc")
        .include("include")
        .std("c++17")
        .flag_if_supported("/fp:strict")
        .flag_if_supported("-fno-fast-math");
    println!("cargo:rerun-if-env-changed=SCR_NATIVE_SANITIZE");
    if let Ok(mode) = env::var("SCR_NATIVE_SANITIZE") {
        if mode != "address" && mode != "address,undefined" {
            panic!("unsupported sanitizer profile");
        }
        if env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default() == "msvc" {
            if mode != "address" {
                panic!("MSVC supports this gate only with address; run undefined on Linux");
            }
            build.flag("/fsanitize=address");
        } else {
            build.flag(format!("-fsanitize={mode}"));
            println!("cargo:rustc-link-arg=-fsanitize={mode}");
        }
    }
    let compiler = build.get_compiler();
    let version = Command::new(compiler.path())
        .arg(if compiler.is_like_msvc() {
            "/Bv"
        } else {
            "--version"
        })
        .output()
        .expect("compiler version");
    let diagnostic = format!(
        "{}{}",
        String::from_utf8_lossy(&version.stdout),
        String::from_utf8_lossy(&version.stderr)
    );
    let mut source = Vec::new();
    for file in [
        "src/ffi.rs",
        "native/kernels.cc",
        "include/kernels.h",
        "build.rs",
        "Cargo.toml",
    ] {
        println!("cargo:rerun-if-changed={file}");
        let bytes = fs::read(file).expect("native source");
        source.extend_from_slice(&(bytes.len() as u64).to_le_bytes());
        source.extend_from_slice(&bytes);
    }
    let source_id =
        execution_commitment::commit("scr.provider.native-source.v1", &[&source]).to_hex();
    println!("cargo:rustc-env=SCR_NATIVE_SOURCE_ID={source_id}");
    let identity = format!(
        "compiler={}\nversion={}\nflags={:?}\nsource={source_id}\n",
        compiler.path().display(),
        diagnostic
            .lines()
            .find(|s| s.contains("Version") || s.contains("version"))
            .unwrap_or("unknown"),
        compiler.args()
    );
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("native-build.txt"),
        identity,
    )
    .unwrap();
    build.compile("scr_provider_kernels");
}
