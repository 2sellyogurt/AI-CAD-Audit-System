; AI-CAD-Audit-System v7.0 NSIS Setup Script
; Usage: makensis /INPUTCHARSET UTF8 setup.nsi

!include "MUI2.nsh"

!define PRODUCT_NAME "AI-CAD-Audit-System"
!define PRODUCT_DISPLAY "AI\u667A\u80FD\u5BA1\u56FE\u7CFB\u7EDF"
!define PRODUCT_VERSION "7.0"
!define PRODUCT_PUBLISHER "AI-CAD"
!define PRODUCT_EXE "AI审图系统.exe"
!define PRODUCT_FOLDER "AI审图系统"
!define SETUP_NAME "AI-CAD-Audit-System-v${PRODUCT_VERSION}-Setup"

OutFile "${SETUP_NAME}.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "Software\${PRODUCT_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

VIProductVersion "7.0.0.0"
VIAddVersionKey "ProductName" "${PRODUCT_DISPLAY}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT_DISPLAY} v${PRODUCT_VERSION} Installer"
VIAddVersionKey "FileVersion" "${PRODUCT_VERSION}"

!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch AI-CAD Audit System"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "Main Program" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite on
    
    File /r "dist\${PRODUCT_FOLDER}\*.*"
    
    CreateDirectory "$INSTDIR\data"
    CreateDirectory "$INSTDIR\logs"
    CreateDirectory "$INSTDIR\output"
    
    IfFileExists "$INSTDIR\.env" SkipEnv
    IfFileExists "$INSTDIR\.env.template" 0 SkipEnv
        CopyFiles "$INSTDIR\.env.template" "$INSTDIR\.env"
    SkipEnv:
    
    WriteRegStr HKLM "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\${PRODUCT_NAME}" "Version" "${PRODUCT_VERSION}"
    
    WriteUninstaller "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_DISPLAY}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "EstimatedSize" 310000
SectionEnd

Section "Desktop Shortcut" SEC02
    CreateShortCut "$DESKTOP\${PRODUCT_DISPLAY}.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
SectionEnd

Section "Start Menu" SEC03
    CreateDirectory "$SMPROGRAMS\${PRODUCT_DISPLAY}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_DISPLAY}\Launch.lnk" "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_DISPLAY}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
    nsExec::ExecToLog 'taskkill /F /IM "${PRODUCT_EXE}"'
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\${PRODUCT_DISPLAY}.lnk"
    RMDir /r "$SMPROGRAMS\${PRODUCT_DISPLAY}"
    DeleteRegKey HKLM "Software\${PRODUCT_NAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
SectionEnd
