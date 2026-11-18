#include <windows.h>
#include <iostream>

extern "C" __declspec(dllexport) void CompileGameData(const char* projectPath) {
    std::cout << "Compiling project at: " << projectPath << std::endl;
}
