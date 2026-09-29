#[path="scr_dsp.rs"] mod bindings;
fn main() {
    let path=std::env::args().nth(1).expect("corpus path");
    let text=std::fs::read_to_string(path).expect("corpus read");
    for line in text.lines().filter(|l| !l.is_empty()) {
        let fields:Vec<&str>=line.split_whitespace().collect();
        let k:usize=fields[0].parse().unwrap();
        let n:usize=fields[1].parse().unwrap();
        let split:usize=fields[2].parse().unwrap();
        assert!(k>=1 && k<=64 && n>=2 && n<=4096 && split>0 && split<n);
        let nums:Vec<f64>=fields[3..].iter().map(|s|s.parse().unwrap()).collect();
        assert_eq!(nums.len(), k+k-1+n);
        let (b,tail)=nums.split_at(k); let (h,x)=tail.split_at(k-1);
        let (y,z)=bindings::fir(b,x,h).unwrap();
        let (mut left,zl)=bindings::fir(b,&x[..split],h).unwrap();
        let (right,zr)=bindings::fir(b,&x[split..],&zl).unwrap();
        left.extend(right); assert_eq!(y,left); assert_eq!(z,zr);
        for v in y.iter().chain(z.iter()) { print!("{:.17e} ",v); } println!();
    }
}
