; Sanad setup (.exe). Built by installer/build.sh:  makensis -DVERSION=x.y.z -DSTAGE=<folder> -DOUT=<file> sanad.nsi
; Per-user install, no administrator rights. The shortcuts start Sanad.exe (no console). The models and the law pack are
; downloaded on the first start, in a setup window (Setup-Sanad.ps1).
Unicode true
!include "MUI2.nsh"

!define APP "Sanad"
!define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sanad"

Name "${APP} ${VERSION}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\Sanad"
InstallDirRegKey HKCU "Software\Sanad" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; the setup wizard keeps its own icon (sanad.ico); the installed app and its shortcuts use app.ico (via Sanad.exe)
!define MUI_ICON "sanad.ico"
!define MUI_UNICON "sanad.ico"
!define MUI_WELCOMEPAGE_TEXT "Sanad answers questions on Moroccan law from the official texts, on your own computer.$\r$\n$\r$\nThis installs the application. On the first start it downloads the law pack and the local models (about 7 GB), so keep an internet connection for that first start."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Start Sanad now (downloads the law pack and the models, about 7 GB)"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchSanad

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Arabic"

Function LaunchSanad
  Exec '"$INSTDIR\Sanad.exe"'
FunctionEnd

Section "Sanad"
  SetShellVarContext current
  RMDir /r "$INSTDIR\backend"
  RMDir /r "$INSTDIR\frontend"
  SetOutPath "$INSTDIR"
  File /r "${STAGE}/*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Sanad" "InstallDir" "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\Sanad"
  CreateShortCut "$SMPROGRAMS\Sanad\Sanad.lnk" "$INSTDIR\Sanad.exe"
  CreateShortCut "$SMPROGRAMS\Sanad\Sanad - repair setup.lnk" "$INSTDIR\Sanad.exe" "--setup"
  CreateShortCut "$SMPROGRAMS\Sanad\Uninstall Sanad.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\Sanad.lnk" "$INSTDIR\Sanad.exe"
  WriteRegStr HKCU "${UNKEY}" "DisplayName" "Sanad"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\Sanad.exe"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0x1000, p 0, p 0)'  ; refresh the icon cache (new icon on the desktop)
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\Sanad\*.lnk"
  RMDir "$SMPROGRAMS\Sanad"
  Delete "$DESKTOP\Sanad.lnk"
  RMDir /r "$INSTDIR"
  RMDir /r "$LOCALAPPDATA\Sanad"
  DeleteRegKey HKCU "${UNKEY}"
  DeleteRegKey HKCU "Software\Sanad"
  MessageBox MB_YESNO|MB_ICONQUESTION "Also delete the law pack, the models and your Sanad data ($PROFILE\.moroccan-legal-rag)?" IDNO +2
  RMDir /r "$PROFILE\.moroccan-legal-rag"
SectionEnd
