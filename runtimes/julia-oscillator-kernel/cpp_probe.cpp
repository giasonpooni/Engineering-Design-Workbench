// Bounded TSV probe and executable tests. All calculations go through the C ABI.
#include "oscillator_cpp.hpp"
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
static void selftest(std::string_view source) {
    ciw::OscillatorKernel kernel;
    require(kernel.rhs({1,-2},{0.25,2}).status == 7,"unbound call accepted");
    require(kernel.bind_source("wrong") == 7,"invalid source accepted");
    require(kernel.bind_source(source) == 0,"valid source refused");
    auto a = kernel.rhs({1,-2},{0.25,2});
    require(a.status == 0 && a.derivative == std::array<double,2>{-2,-3},"mixed state differs");
    auto b = kernel.rhs({2,3},{0,2});
    require(b.status == 0 && b.derivative == std::array<double,2>{3,-8},"undamped state differs");
    require(kernel.rhs({std::numeric_limits<double>::quiet_NaN(),0},{0,1}).status == 3,"NaN accepted");
    require(kernel.rhs({0,0},{1,1}).status == 4,"invalid parameters accepted");
    require(kernel.rhs({1e7,0},{0,1}).status == 4,"invalid state accepted");
    require(kernel.bind_source(std::string(64,'0')) == 7,"wrong source accepted");
    require(kernel.rhs({1,-2},{0.25,2}).status == 7,"failed rebind retained authority");
    require(kernel.bind_source(source) == 0 && kernel.rhs({1,-2},{0.25,2}).derivative == a.derivative,
            "refusal corrupted subsequent call");
    std::cout << "cpp-wrapper-tests: 11 passed\n";
}
static double number(std::string_view text) {
    double value = 0;
    const auto result = std::from_chars(text.data(),text.data()+text.size(),value);
    require(result.ec == std::errc{} && result.ptr == text.data()+text.size(),"invalid scalar");
    return value;
}
int main(int argc, char **argv) {
    try {
        require(argc == 2 || (argc == 3 && std::string_view(argv[2]) == "--selftest"),
                "usage: cpp-probe SOURCE_SHA256 [--selftest]");
        if (argc == 3) { selftest(argv[1]); return 0; }
        ciw::OscillatorKernel kernel;
        require(kernel.bind_source(argv[1]) == 0,"source or ABI mismatch");
        std::string input;
        char ch;
        while (std::cin.get(ch)) {
            require(input.size() < 1048576,"input exceeds byte limit");
            input.push_back(ch);
        }
        require(!std::cin.bad(),"input read failed");
        std::istringstream lines(input);
        std::string line;
        std::vector<std::array<double,2>> outputs;
        while (std::getline(lines,line)) {
            require(outputs.size() < 4096,"input exceeds row limit");
            std::array<double,4> values{};
            size_t start = 0;
            for (size_t i=0; i<4; ++i) {
                const size_t end = line.find('\t',start);
                require((i == 3) == (end == std::string::npos),"expected four TSV fields");
                values[i] = number(std::string_view(line).substr(start,end == std::string::npos ? end : end-start));
                start = end + 1;
            }
            const auto result = kernel.rhs({values[0],values[1]},{values[2],values[3]});
            require(result.status == 0,"native RHS refused input");
            outputs.push_back(result.derivative);
        }
        require(!outputs.empty(),"empty input");
        // Nothing is printed until every input row is accepted.
        std::cout.imbue(std::locale::classic());
        std::cout << std::scientific << std::setprecision(17);
        for (const auto& row : outputs) std::cout << row[0] << '\t' << row[1] << '\n';
        return std::cout.good() ? 0 : 2;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 2;
    }
}
