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
