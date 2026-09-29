#include "scr_dsp.hpp"
#include <fstream>
#include <iostream>
#include <iomanip>
int main(int argc,char** argv) {
    if(argc!=2) return 1;
    std::ifstream in(argv[1]); size_t k,n,split;
    std::cout << std::setprecision(17);
    while(in>>k>>n>>split) {
        if(k<1||k>64||n<2||n>4096||split<1||split>=n) return 2;
        std::vector<double> b(k), h(k-1), x(n);
        for(auto* p:{&b,&h,&x}) for(auto& v:*p) if(!(in>>v)) return 3;
        auto [whole,z]=scr_dsp::fir(b,x,h);
        auto [left,zl]=scr_dsp::fir(b,std::vector<double>(x.begin(),x.begin()+split),h);
        auto [right,zr]=scr_dsp::fir(b,std::vector<double>(x.begin()+split,x.end()),zl);
        left.insert(left.end(),right.begin(),right.end());
        if(whole!=left||z!=zr) return 4;
        for(auto v:whole) std::cout << v << ' ';
        for(auto v:z) std::cout << v << ' ';
        std::cout << '\n';
    }
    return in.eof()?0:5;
}
