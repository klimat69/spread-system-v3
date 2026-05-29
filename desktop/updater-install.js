const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const MAC_APP_BUNDLE_NAME = "Spread System v3.app";
const DEFAULT_MAC_INSTALL_PATH = path.join("/Applications", MAC_APP_BUNDLE_NAME);
const UPDATER_CACHE_DIR = "spread-system-v3-desktop-updater";

function appendUpdaterLog(updaterLogPath, message) {
  if (!updaterLogPath) return;
  try {
    fs.appendFileSync(updaterLogPath, `[${new Date().toISOString()}] ${message}\n`, "utf-8");
  } catch (_e) {
    // ignore
  }
}

function updaterCacheRoots(userDataDir) {
  const home = path.dirname(path.dirname(userDataDir));
  return [
    path.join(home, "Library", "Caches", UPDATER_CACHE_DIR),
    path.join(userDataDir, "..", "Caches", UPDATER_CACHE_DIR),
    path.join(userDataDir, `${UPDATER_CACHE_DIR}`)
  ];
}

function findNewestFileInDir(dir, extension) {
  if (!fs.existsSync(dir)) return null;
  const matches = fs
    .readdirSync(dir)
    .filter((name) => name.toLowerCase().endsWith(extension))
    .map((name) => path.join(dir, name))
    .filter((candidate) => {
      try {
        return fs.statSync(candidate).isFile();
      } catch (_e) {
        return false;
      }
    });
  if (!matches.length) return null;
  matches.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return matches[0];
}

function findPendingArtifact(userDataDir, extension) {
  const ext = extension.startsWith(".") ? extension : `.${extension}`;
  for (const root of updaterCacheRoots(userDataDir)) {
    const pending = path.join(root, "pending");
    const hit = findNewestFileInDir(pending, ext);
    if (hit) return hit;
    const hitRoot = findNewestFileInDir(root, ext);
    if (hitRoot) return hitRoot;
  }
  return null;
}

function resolveMacAppBundlePath(app) {
  try {
    const exe = app.getPath("exe");
    const bundle = path.resolve(exe, "..", "..", "..");
    if (bundle.endsWith(".app") && fs.existsSync(bundle)) {
      return bundle;
    }
  } catch (_e) {
    // fall through
  }
  if (fs.existsSync(DEFAULT_MAC_INSTALL_PATH)) {
    return DEFAULT_MAC_INSTALL_PATH;
  }
  return DEFAULT_MAC_INSTALL_PATH;
}

function findMacAppBundleInDir(rootDir, maxDepth = 4) {
  if (!fs.existsSync(rootDir)) return null;
  const queue = [{ dir: rootDir, depth: 0 }];
  while (queue.length) {
    const { dir, depth } = queue.shift();
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (_e) {
      continue;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory() && entry.name === MAC_APP_BUNDLE_NAME) {
        return full;
      }
      if (entry.isDirectory() && depth < maxDepth) {
        queue.push({ dir: full, depth: depth + 1 });
      }
    }
  }
  return null;
}

function stopAllProcessesForUpdate(backendProcess) {
  if (backendProcess) {
    try {
      if (process.platform === "win32") {
        spawnSync("taskkill", ["/F", "/T", "/PID", String(backendProcess.pid)], { stdio: "ignore" });
      } else {
        backendProcess.kill("SIGTERM");
      }
    } catch (_e) {
      // ignore
    }
  }
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/F", "/IM", "spread-backend.exe"], { stdio: "ignore" });
  } else if (process.platform === "darwin") {
    spawnSync("pkill", ["-f", "spread-backend"], { stdio: "ignore" });
  }
}

function installPendingMacUpdate({ app, userDataDir, updaterLogPath, backendProcess, onQuit }) {
  const zipPath = findPendingArtifact(userDataDir, ".zip");
  if (!zipPath) {
    return { ok: false, message: "Файл обновления не найден. Дождитесь загрузки до 100%." };
  }

  const installTarget = resolveMacAppBundlePath(app);
  const extractDir = path.join(app.getPath("temp"), `spread-update-${Date.now()}`);
  const scriptPath = path.join(app.getPath("temp"), `spread-install-${Date.now()}.sh`);
  const logFile = updaterLogPath || path.join(path.dirname(userDataDir), "logs", "updater-install.log");

  const script = `#!/bin/bash
set -u
LOG="${logFile.replace(/"/g, '\\"')}"
ZIP="${zipPath.replace(/"/g, '\\"')}"
EXTRACT="${extractDir.replace(/"/g, '\\"')}"
TARGET="${installTarget.replace(/"/g, '\\"')}"
BUNDLE_NAME="${MAC_APP_BUNDLE_NAME}"
PARENT_PID="${process.pid}"

log() { echo "[$(date -Iseconds)] $1" >> "$LOG"; }

log "mac update install start zip=$ZIP target=$TARGET"
sleep 1
kill "$PARENT_PID" 2>/dev/null || true
pkill -f "spread-backend" 2>/dev/null || true
sleep 1
mkdir -p "$EXTRACT"
if ! /usr/bin/unzip -oq "$ZIP" -d "$EXTRACT"; then
  log "unzip failed"
  exit 1
fi
FOUND=""
if [ -d "$EXTRACT/$BUNDLE_NAME" ]; then
  FOUND="$EXTRACT/$BUNDLE_NAME"
else
  FOUND="$(/usr/bin/find "$EXTRACT" -maxdepth 4 -type d -name "$BUNDLE_NAME" | /usr/bin/head -n 1)"
fi
if [ -z "$FOUND" ] || [ ! -d "$FOUND" ]; then
  log "app bundle not found in zip"
  exit 2
fi
TARGET_DIR="$(/usr/bin/dirname "$TARGET")"
mkdir -p "$TARGET_DIR" 2>/dev/null || true
rm -rf "$TARGET"
if ! /usr/bin/ditto "$FOUND" "$TARGET"; then
  log "ditto failed"
  exit 3
fi
/usr/bin/xattr -cr "$TARGET" 2>/dev/null || true
/usr/bin/open "$TARGET"
log "mac update install done"
rm -rf "$EXTRACT"
rm -f "$0"
`;

  fs.writeFileSync(scriptPath, script, { mode: 0o755 });
  appendUpdaterLog(updaterLogPath, `Manual macOS install zip=${zipPath} target=${installTarget}`);
  stopAllProcessesForUpdate(backendProcess);
  const child = spawn("/bin/bash", [scriptPath], { detached: true, stdio: "ignore" });
  child.unref();
  setTimeout(() => onQuit(), 300);
  return {
    ok: true,
    message: "Установка запущена. Приложение перезапустится через несколько секунд."
  };
}

function applyPendingUpdate({ app, isPackaged, autoUpdater, userDataDir, updaterLogPath, backendProcess, onQuit }) {
  if (!isPackaged || !autoUpdater) {
    return { ok: false, message: "Установка обновления недоступна в dev-режиме." };
  }

  if (process.platform === "darwin") {
    const zipPath = findPendingArtifact(userDataDir, ".zip");
    if (zipPath) {
      return installPendingMacUpdate({ app, userDataDir, updaterLogPath, backendProcess, onQuit });
    }
    return { ok: false, message: "ZIP обновления не найден. Повторите проверку обновлений." };
  }

  if (process.platform === "win32") {
    const installerPath = findPendingArtifact(userDataDir, ".exe");
    if (!installerPath) {
      return {
        ok: false,
        message: "Установщик обновления не найден. Дождитесь окончания загрузки (100%)."
      };
    }
    appendUpdaterLog(updaterLogPath, `Windows install via quitAndInstall exe=${installerPath}`);
    stopAllProcessesForUpdate(backendProcess);
    setTimeout(() => {
      try {
        autoUpdater.quitAndInstall(false, true);
      } catch (error) {
        appendUpdaterLog(updaterLogPath, `quitAndInstall failed: ${error?.message || String(error)}`);
      }
      setTimeout(() => onQuit(), 800);
    }, 600);
    return { ok: true, message: "Запуск установщика Windows. Приложение закроется." };
  }

  appendUpdaterLog(updaterLogPath, "Applying update via quitAndInstall (generic)");
  stopAllProcessesForUpdate(backendProcess);
  autoUpdater.quitAndInstall(false, true);
  return { ok: true };
}

module.exports = {
  MAC_APP_BUNDLE_NAME,
  findPendingArtifact,
  resolveMacAppBundlePath,
  findMacAppBundleInDir,
  stopAllProcessesForUpdate,
  installPendingMacUpdate,
  applyPendingUpdate
};
