# Installation Instructions for Colr Pak

## Instruction for Linux

1. Open your browser and go to Colr Pak  [Release Section](https://github.com/mitradranirban/colr-pak/releases/latest)

2. Under Assets, download the  Linux   file `colrpak-linux.tar.gz` or `colrpak-linux-arm64.tar.gz`

3. Right click and select Extract

4. Inside the extracted colrpak-linux folder, click on colrpak app

5. In the confirmation dialog click `Execute`.


The ready-made apps are not code signed so require special treatment in MS Windows and MacOS


## Instructions for Windows (10 or 11)

### Step 1: Enable Developer Mode
1. Open Settings → Privacy & Security → For developers (Windows 11), or Settings → Update & Security → For developers (Windows 10)

2. Toggle Developer Mode to On

3. Click Yes when prompted and restart your PC

### Step 2: Download the App

1. Open your browser and go to: [Release Section](https://github.com/mitradranirban/colr-pak/releases/latest)

2. Under Assets, download the  Windows app file `colrpak-windows.zip`

3. Save it to a known location, e.g. your Downloads folder

### Step 3: Unblock the Downloaded File
Windows may quarantine files downloaded from the internet:

1. Extract the zip file by right-clicking and selecting Extract

2. Right-click the downloaded file → select Properties

3. On the General tab, look for an "Unblock" checkbox at the bottom

4. Check Unblock, then click Apply → OK

###  Step 4: Install the App

1. Double-click the .exe

2. If a blue "Windows protected your PC" SmartScreen dialog appears, click More info

3. Click "Run anyway"

## Instructions for MacOS

Due to quarantine issues of unsigned apps in MacOS it is peferably installed through homebrew
### Step 1: Install Homebrew

If you don't have Homebrew yet, install it by running this in Terminal:
​
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
### Step 2: Add the Custom Tap
Since colr-pak is distributed via a third-party tap (not the main Homebrew repository), you must add it first:
```
brew tap mitradranirban/tap
```

### Step 3: Install colr-pak

Install the app using the --cask flag and remove quarantine for macOS Gatekeeper for this unsigned app:
```
bash
brew install --cask mitradranirban/tap/colr-pak
xattr -dr com.apple.quarantine "/Applications/Colr Pak.app"
```

   Note: The --no-quarantine flag is needed because colr-pak is currently unsigned. Without it, macOS will block the app from launching with a "developer cannot be verified" error

### Step 4: If the App Still Won't Open
On Apple Silicon Macs (M1/M2/M3), the quarantine attribute sometimes persists even after installation. If you see a "colr-pak is damaged and can't be opened" message, remove it manually by writing this command in terminal:
```
sudo xattr -dr com.apple.quarantine /Applications/Colr Pak.app
```

Alternatively, you can right-click the app in Finder → Open → click Open in the dialog to approve it once.

### Step 5: Build from source

If it still doesn't work in Apple M1/M2/M3 etc for Apple gatekeeper policy, you can build from source as indicated in README which will self sign your app.
### Step 6: Launch colr-pak

Open colr-pak from your Applications folder or via Launchpad



The app starts a local Fontra server and automatically opens in your browser for editing COLRv1 color fonts
