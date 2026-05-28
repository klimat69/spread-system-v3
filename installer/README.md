# Installer Builds

The desktop app uses Electron Builder and writes release artifacts to `installer/dist`.

```bash
cd desktop
npm install
npm run build:win
npm run build:mac
npm run build:linux
```

Expected artifact names:

- Windows: `spread-system-v3-setup.exe`
- macOS: `spread-system-v3.dmg`
- Linux: `spread-system-v3.AppImage`

The Windows NSIS installer is configured for EN/RU installer languages, a selectable install path, Start Menu shortcut, and desktop shortcut creation.

## Installer Runtime Bundling
The desktop build includes a bundled backend executable (built via PyInstaller) so end users do not need to install Python.
The build scripts also package the React frontend (`frontend/dist`) and the backend runtime (`backend-runtime`).

## What to Verify
After building an installer:
- Run a clean install on a fresh machine/user profile.
- Launch the app and complete the in-app setup wizard (no terminal required).
- Confirm logs persist and can be exported/cleared.
- Confirm uninstall removes the app and shortcuts.
# Installer Builds

Spread System v3 uses Electron Builder from the `desktop` package.

Build targets:

- Windows: `spread-system-v3-setup.exe`
- macOS: `spread-system-v3.dmg`
- Linux: `spread-system-v3.AppImage`

Run from the project root:

```bash
npm run build:frontend
npm run build:desktop
```

Cross-platform signing and notarization are intentionally left to the release environment. The local build scripts produce unsigned artifacts suitable for internal testing.

## End-user install flow (no terminal)

This project supports a true installer flow for end users:

- You (builder) run one command to produce artifacts:
  - macOS: `npm run release:mac`
  - Windows: `npm run release:win`
  - Linux: `npm run release:linux`
- You send your user only the installer artifact from `installer/dist`.
- The user installs and launches the app with no terminal commands.

Important:

- On macOS, distribute the generated `.dmg` (not a zipped `.app`).
- If the app is unsigned/not notarized, Gatekeeper may show a warning; this is an OS trust prompt, not a runtime dependency issue.
