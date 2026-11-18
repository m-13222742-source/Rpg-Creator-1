#include <windows.h>
#include <string>

extern "C" __declspec(dllexport) bool LoadCustomPlugin(const char* pluginPath) {
    return true;
}
