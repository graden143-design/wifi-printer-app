name: Build, Sign and Create Inno Setup Installer

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest

    steps:
    - name: Checkout Code
      uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install Dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pyinstaller pywin32 pillow pypdf fitz

    - name: Build Executable with PyInstaller
      run: |
        pyinstaller --noconfirm --onedir --windowed --name "BenozirPrintStation" --icon=NONE main_server.py

    - name: Sign Binary Executable
      shell: powershell
      run: |
        if ("${{ secrets.BASE64_PFX_CERT }}" -ne "") {
          echo "${{ secrets.BASE64_PFX_CERT }}" > cert.pfx.b64
          certutil -decode cert.pfx.b64 cert.pfx
          & "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" sign /f cert.pfx /p "${{ secrets.CERT_PASSWORD }}" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist/BenozirPrintStation/BenozirPrintStation.exe"
        } else {
          Write-Host "No Code Signing Certificate found in secrets. Skipping signing..."
        }

    - name: Install Inno Setup
      run: |
        choco install innosetup -y

    - name: Compile Inno Setup Script
      run: |
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer_script.iss

    - name: Upload Installer Artifact
      uses: actions/upload-artifact@v3
      with:
        name: BenozirPrintStation-Setup
        path: Output/*.exe
