// Protocol-only scripted child. It never runs Julia or interval arithmetic.
use std::{fs, io::{self, Read, Write}, path::Path, time::Duration};
fn read(input: &mut impl Read) -> Option<Vec<u8>> {
    let mut header = [0; 4];
    input.read_exact(&mut header).ok()?;
    let size = u32::from_be_bytes(header) as usize;
    assert!(size <= 1_048_576);
    let mut data = vec![0; size];
    input.read_exact(&mut data).unwrap();
    Some(data)
}
fn write(output: &mut impl Write, bytes: &[u8]) {
    output.write_all(&(bytes.len() as u32).to_be_bytes()).unwrap();
    output.write_all(bytes).unwrap();
    output.flush().unwrap();
}
fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert_eq!(args.len(), 4);
    assert_eq!(args[0], "--startup-file=no");
    assert_eq!(args[1], "--history-file=no");
    assert_eq!(std::env::var("JULIA_NUM_THREADS").unwrap(), "1");
    assert_eq!(std::env::var("JULIA_PKG_OFFLINE").unwrap(), "true");
    let worker = Path::new(&args[3]);
    let project = worker.parent().unwrap();
    assert_eq!(args[2], format!("--project={}",project.display()));
    let mut names: Vec<_> = fs::read_dir(project).unwrap().map(|e| e.unwrap().file_name().into_string().unwrap()).collect();
    names.sort();
    assert_eq!(names, ["Manifest.toml","Project.toml","worker.jl"]);
    let mode = fs::read_to_string(worker).unwrap();
    let frames = fs::read(std::env::var("SCR_INTERVAL_FIXTURE_FRAMES").unwrap()).unwrap();
    let mut scripted = frames.as_slice();
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    read(&mut input).unwrap();
    write(&mut output, &read(&mut scripted).unwrap());
    while read(&mut input).is_some() {
        match mode.trim() {
            "timeout" => std::thread::sleep(Duration::from_secs(60)),
            "stderr" => { io::stderr().write_all(&vec![b'x';70_000]).unwrap(); std::thread::sleep(Duration::from_secs(60)); },
            "crash" => std::process::exit(9),
            "truncated" => { output.write_all(&100u32.to_be_bytes()).unwrap(); output.write_all(b"a").unwrap(); return; },
            _ => write(&mut output, &read(&mut scripted).unwrap()),
        }
    }
}
