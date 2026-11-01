cmake_minimum_required(VERSION 3.16)
project(golden_ntt)

set(CMAKE_CXX_STANDARD 11)

add_executable(test_ntt_model
    ntt_model.cpp
    test_ntt_model.cpp
)

enable_testing()
add_test(NAME golden_ntt_test COMMAND test_ntt_model)
