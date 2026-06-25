﻿﻿﻿; ============================================================
; AI-CAD-Audit-System v7.0 NSIS Installer
; ============================================================
Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!define PRODUCT_NAME "AI-CAD-Audit-System"
!define PRODUCT_VERSION "7.0"
!define PRODUCT_PUBLISHER "AI-CAD-Audit-Team"

Name "${PRODUCT_NAME} v${PRODUCT_VERSION}"
OutFile "AI-CAD-Audit-System-v7.0-Setup.exe"
InstallDir "$PROGRAMFILES\AI-CAD-Audit-System"
RequestExecutionLevel admin

!define MUI_ABORTWARNING
!define MUI_ICON "app_icon.ico"
!define MUI_UNICON "app_icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\launch.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Start AI-CAD-Audit-System"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
  SetOutPath "$INSTDIR"
  
  File "launch.bat"
  File "requirements.txt"
  File ".env.template"
  File "README.md"
  File "app_icon.ico"
  
  SetOutPath "$INSTDIR\src"
  File /r /x "__pycache__" /x "*.pyc" /x "v7_data.db" /x "*.db-shm" /x "*.db-wal" /x ".admin_password" /x ".encrypted_keys.json" /x "input" /x "output_v7.0" "src\*.*"
  
  CreateDirectory "$INSTDIR\src\v7\input"
  CreateDirectory "$INSTDIR\src\v7\output_v7.0"
  
  SetOutPath "$INSTDIR\.venv"
  File /r /x "__pycache__" ".venv\*.*"
  
  WriteUninstaller "$INSTDIR\uninst.exe"
  
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\AI-CAD-Audit-System.lnk" "$INSTDIR\launch.bat" "" "$INSTDIR\app_icon.ico"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\uninst.exe"
  CreateShortCut "$DESKTOP\AI-CAD-Audit-System.lnk" "$INSTDIR\launch.bat" "" "$INSTDIR\app_icon.ico"
  
  WriteRegStr HKLM "Software\${PRODUCT_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_NAME} v${PRODUCT_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayIcon" "$INSTDIR\app_icon.ico"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "NoRepair" 1
  
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\launch.bat"
  Delete "$INSTDIR\requirements.txt"
  Delete "$INSTDIR\.env.template"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\app_icon.ico"
  Delete "$INSTDIR\uninst.exe"
  RMDir /r "$INSTDIR\src"
  RMDir /r "$INSTDIR\.venv"
  Delete "$DESKTOP\AI-CAD-Audit-System.lnk"
  RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"
  DeleteRegKey HKLM "Software\${PRODUCT_NAME}"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
  RMDir "$INSTDIR"
SectionEnd
