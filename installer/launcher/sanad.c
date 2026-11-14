/* Sanad.exe: the program the shortcuts start.  A Windows (not console) program, so no black window ever shows.
 *
 *   - Sanad already open        -> brings its window to the front
 *   - everything is installed   -> starts  <runtime>\venv\Scripts\pythonw.exe -m legalrag.desktop --app-dir <this folder>
 *   - first start, or --setup   -> runs Start-Sanad.ps1 in a hidden PowerShell, which shows the setup window and then starts the app
 *
 * After an update it also asks Windows once to refresh its icon cache, so the desktop shortcut shows the new icon.
 * <runtime> is %LOCALAPPDATA%\Sanad.   Build:  x86_64-w64-mingw32-gcc -municode -mwindows -O2 sanad.c sanad.res -o Sanad.exe
 */
#include <windows.h>
#include <shlobj.h>
#include <wchar.h>

#define BUF 2048

static BOOL exists(const wchar_t *path) {
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static BOOL run(wchar_t *cmd, const wchar_t *cwd, DWORD flags) {
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, flags, NULL, cwd, &si, &pi)) return FALSE;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return TRUE;
}

#ifndef SANAD_VERSION
#define SANAD_VERSION L"dev"
#endif

/* Windows keeps showing a shortcut's old icon after an update (it caches icons by path): refresh once per version. */
static void refresh_icons_once(void) {
    HKEY k;
    wchar_t seen[64] = L"";
    DWORD size = sizeof seen, type = 0;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\Sanad", 0, NULL, 0, KEY_READ | KEY_WRITE, NULL, &k, NULL) != ERROR_SUCCESS) return;
    if (RegQueryValueExW(k, L"IconsRefreshedFor", NULL, &type, (BYTE *)seen, &size) != ERROR_SUCCESS || type != REG_SZ || wcscmp(seen, SANAD_VERSION) != 0) {
        SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSHNOWAIT, NULL, NULL);
        RegSetValueExW(k, L"IconsRefreshedFor", 0, REG_SZ, (const BYTE *)SANAD_VERSION, (DWORD)((wcslen(SANAD_VERSION) + 1) * sizeof(wchar_t)));
    }
    RegCloseKey(k);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    wchar_t app[BUF], runtime[BUF], py[BUF], done[BUF], cmd[BUF * 3], windir[BUF];
    BOOL setup = args && wcsstr(args, L"--setup") != NULL;
    (void)inst; (void)prev; (void)show;
    refresh_icons_once();

    if (!setup) { /* already open: bring it to the front */
        HWND w = FindWindowW(NULL, L"Sanad");
        if (!w) w = FindWindowW(NULL, L"Sanad - setup");
        if (w) {
            if (IsIconic(w)) ShowWindow(w, SW_RESTORE);
            SetForegroundWindow(w);
            return 0;
        }
    }
    CreateMutexW(NULL, FALSE, L"Local\\SanadDesktopApp"); /* a second click while the first start is still loading does nothing */
    if (GetLastError() == ERROR_ALREADY_EXISTS) return 0;

    GetModuleFileNameW(NULL, app, BUF);
    *wcsrchr(app, L'\\') = 0;
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", runtime, BUF - 64)) return 1;
    wcscat(runtime, L"\\Sanad");
    swprintf(py, BUF, L"%ls\\venv\\Scripts\\pythonw.exe", runtime);
    swprintf(done, BUF, L"%ls\\setup-done.txt", runtime);
    SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", L"1");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");

    if (!setup && exists(py) && exists(done)) {
        swprintf(cmd, BUF * 3, L"\"%ls\" -m legalrag.desktop --app-dir \"%ls\"", py, app);
        if (run(cmd, runtime, 0)) {
            Sleep(15000); /* keep the guard above until the window exists */
            return 0;
        }
    }

    GetWindowsDirectoryW(windir, BUF);
    swprintf(cmd, BUF * 3,
             L"\"%ls\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%ls\\Start-Sanad.ps1\"%ls",
             windir, app, setup ? L" -Repair" : L"");
    if (!run(cmd, app, CREATE_NO_WINDOW)) {
        MessageBoxW(NULL, L"Sanad could not start Windows PowerShell, which the first-time setup needs.", L"Sanad", MB_ICONERROR);
        return 1;
    }
    Sleep(15000);
    return 0;
}
