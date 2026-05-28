const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");
let autoUpdater = null;
try {
  ({ autoUpdater } = require("electron-updater"));
} catch (_e) {
  autoUpdater = null;
}
let keytar;
try {
  // keytar is an optional native dependency for production builds.
  keytar = require("keytar");
} catch (_e) {
  keytar = null;
}

let mainWindow;
let backendProcess = null;
let backendLogPath = null;
let updaterLogPath = null;
let updaterInterval = null;

const isPackaged = app.isPackaged;
const projectRoot = isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
const backendRoot = path.join(projectRoot, "backend");
const frontendIndex = isPackaged ? path.join(process.resourcesPath, "frontend", "dist", "index.html") : "http://127.0.0.1:5173";
const userDataDir = app.getPath("userData");
const runtimeDataDir = path.join(userDataDir, "data");
const runtimeLogsDir = path.join(userDataDir, "logs");
const KEYCHAIN_SERVICE = "spread-system-v3";

// Some macOS systems render a black/blank Electron window with GPU compositing enabled.
// Disable hardware acceleration for stable first-run rendering.
app.disableHardwareAcceleration();

ipcMain.handle("keychain-get-credentials", async (_event, { exchange }) => {
  try {
    if (!keytar) return null;
    const raw = await keytar.getPassword(KEYCHAIN_SERVICE, String(exchange).toLowerCase());
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
});

ipcMain.handle("keychain-set-credentials", async (_event, { exchange, apiKey, apiSecret, password }) => {
  try {
    if (!keytar) return { status: "SKIPPED_NO_KEYTAR" };
    const account = String(exchange).toLowerCase();
    const payload = JSON.stringify({
      apiKey: apiKey ?? "",
      apiSecret: apiSecret ?? "",
      password: password ?? ""
    });
    await keytar.setPassword(KEYCHAIN_SERVICE, account, payload);
    return { status: "OK" };
  } catch (e) {
    return { status: "ERROR", message: e?.message || "failed to save credentials" };
  }
});

ipcMain.handle("keychain-clear-credentials", async (_event, { exchange }) => {
  try {
    if (!keytar) return { status: "SKIPPED_NO_KEYTAR" };
    const account = String(exchange).toLowerCase();
    await keytar.deletePassword(KEYCHAIN_SERVICE, account);
    return { status: "OK" };
  } catch (e) {
    return { status: "ERROR", message: e?.message || "failed to clear credentials" };
  }
});

function backendBinaryPath() {
  if (process.platform === "win32") return path.join(projectRoot, "backend-runtime", "spread-backend.exe");
  return path.join(projectRoot, "backend-runtime", "spread-backend");
}

function resolvePackagedBackendBinary() {
  const binaryName = process.platform === "win32" ? "spread-backend.exe" : "spread-backend";
  const candidates = [
    path.join(process.resourcesPath, "backend-runtime", binaryName),
    path.join(process.resourcesPath, binaryName),
    path.join(process.resourcesPath, "app.asar.unpacked", "backend-runtime", binaryName),
    path.join(path.dirname(process.execPath), "..", "Resources", "backend-runtime", binaryName)
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function pythonCommand() {
  return process.env.SPREAD_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

function packagedBackendRoot() {
  return path.join(process.resourcesPath, "backend");
}

function resolveWindowsEmbedPython() {
  const candidates = [
    path.join(process.resourcesPath, "windows-python-embed", "python.exe"),
    path.join(process.resourcesPath, "app.asar.unpacked", "windows-python-embed", "python.exe")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function ensureWindowsPythonDeps(pythonExe, logStream) {
  const marker = path.join(runtimeDataDir, ".win-python-deps-v1");
  if (fs.existsSync(marker)) return true;

  logStream.write("\nPreparing Windows Python runtime (first launch may take a few minutes)...\n");
  const getPip = path.join(process.resourcesPath, "windows-python-embed", "get-pip.py");
  const requirements = path.join(process.resourcesPath, "requirements.txt");
  const sitePackages = path.join(path.dirname(pythonExe), "Lib", "site-packages");

  if (fs.existsSync(getPip)) {
    const pipBootstrap = spawnSync(pythonExe, [getPip, "--no-warn-script-location"], {
      env: { ...process.env, PYTHONPATH: sitePackages },
      stdio: ["ignore", "pipe", "pipe"]
    });
    logStream.write(pipBootstrap.stdout?.toString() || "");
    logStream.write(pipBootstrap.stderr?.toString() || "");
    if (pipBootstrap.status !== 0) {
      logStream.write(`\nget-pip failed with code ${pipBootstrap.status}\n`);
      return false;
    }
  }

  if (fs.existsSync(requirements)) {
    const pipInstall = spawnSync(
      pythonExe,
      ["-m", "pip", "install", "--no-warn-script-location", "-r", requirements],
      {
        env: { ...process.env, PYTHONPATH: sitePackages },
        stdio: ["ignore", "pipe", "pipe"]
      }
    );
    logStream.write(pipInstall.stdout?.toString() || "");
    logStream.write(pipInstall.stderr?.toString() || "");
    if (pipInstall.status !== 0) {
      logStream.write(`\npip install failed with code ${pipInstall.status}\n`);
      return false;
    }
  }

  fs.writeFileSync(marker, new Date().toISOString(), "utf-8");
  return true;
}

function ensureRuntimeFiles() {
  fs.mkdirSync(runtimeDataDir, { recursive: true });
  fs.mkdirSync(runtimeLogsDir, { recursive: true });

  // Ship config.example.json and copy it to userData/config.json on first run.
  const srcExample = path.join(projectRoot, "data", "config.example.json");
  const dstConfig = path.join(runtimeDataDir, "config.json");
  if (!fs.existsSync(dstConfig) && fs.existsSync(srcExample)) {
    fs.copyFileSync(srcExample, dstConfig);
  }
}

function readRuntimeConfig() {
  try {
    const configPath = path.join(runtimeDataDir, "config.json");
    const raw = fs.readFileSync(configPath, "utf-8");
    return JSON.parse(raw);
  } catch (_e) {
    return null;
  }
}

async function injectCredentialsFromKeychain() {
  if (!keytar) return;
  const config = readRuntimeConfig();
  const exchangeName = config?.exchange?.name;
  if (!exchangeName) return;

  const raw = await keytar.getPassword(KEYCHAIN_SERVICE, String(exchangeName).toLowerCase());
  if (!raw) return;

  const creds = JSON.parse(raw);

  await new Promise((resolve) => {
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: 8000,
        path: "/credentials",
        method: "POST",
        headers: { "Content-Type": "application/json" },
        timeout: 5000
      },
      (res) => {
        if ((res.statusCode || 500) >= 400) {
          resolve(false);
          return;
        }
        res.on("data", () => {});
        res.on("end", () => resolve(true));
      }
    );

    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });

    req.write(
      JSON.stringify({
        exchange: exchangeName,
        api_key: creds.apiKey ?? "",
        api_secret: creds.apiSecret ?? "",
        password: creds.password ?? ""
      })
    );
    req.end();
  });
}

function canConnect(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port, timeout: 500 }, () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
    socket.on("timeout", () => {
      socket.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(port = 8000, attempts = 180) {
  for (let i = 0; i < attempts; i += 1) {
    if (await canConnect(port)) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function startBackend() {
  if (backendProcess) return true;
  ensureRuntimeFiles();

  backendLogPath = path.join(runtimeLogsDir, "backend.log");
  const logStream = fs.createWriteStream(backendLogPath, { flags: "a" });
  const binaryPath = isPackaged ? resolvePackagedBackendBinary() : backendBinaryPath();
  const canRunBinary = Boolean(binaryPath && fs.existsSync(binaryPath));

  if (canRunBinary) {
    backendProcess = spawn(binaryPath, [], {
      env: {
        ...process.env,
        SPREAD_SYSTEM_DATA_DIR: runtimeDataDir,
        SPREAD_BACKEND_HOST: "127.0.0.1",
        SPREAD_BACKEND_PORT: "8000"
      },
      stdio: ["ignore", "pipe", "pipe"]
    });
    backendProcess.on("error", (error) => {
      logStream.write(`\nbackend spawn error: ${error?.message || "unknown"}\n`);
    });
  } else if (isPackaged && process.platform === "win32") {
    const embedPy = resolveWindowsEmbedPython();
    const backendDir = packagedBackendRoot();
    if (!embedPy || !fs.existsSync(backendDir)) {
      logStream.write(`\nWindows runtime missing (embed python or backend sources)\n`);
      dialog.showErrorBox(
        "Backend runtime missing",
        "Windows runtime files were not found in the installed app. Reinstall from spread-system-v3-setup.exe."
      );
      logStream.end();
      backendProcess = null;
      return false;
    }
    if (!ensureWindowsPythonDeps(embedPy, logStream)) {
      dialog.showErrorBox(
        "Backend setup failed",
        "Could not prepare Python dependencies on first launch. Check logs in %APPDATA%\\spread-system-v3-desktop\\logs\\backend.log"
      );
      logStream.end();
      backendProcess = null;
      return false;
    }
    const sitePackages = path.join(path.dirname(embedPy), "Lib", "site-packages");
    backendProcess = spawn(
      embedPy,
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
      {
        cwd: backendDir,
        env: {
          ...process.env,
          PYTHONPATH: `${backendDir}${path.delimiter}${sitePackages}`,
          SPREAD_SYSTEM_DATA_DIR: runtimeDataDir
        },
        stdio: ["ignore", "pipe", "pipe"]
      }
    );
    backendProcess.on("error", (error) => {
      logStream.write(`\nbackend spawn error: ${error?.message || "unknown"}\n`);
    });
  } else if (isPackaged) {
    logStream.write(`\npackaged backend binary missing (expected near ${process.resourcesPath})\n`);
    dialog.showErrorBox(
      "Backend runtime missing",
      "The bundled backend executable was not found in the installed app. Rebuild with `npm --prefix desktop run build:mac` and install from the generated DMG."
    );
    logStream.end();
    backendProcess = null;
    return false;
  } else {
    // Dev mode and fallback: require system python.
    backendProcess = spawn(
      pythonCommand(),
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
      {
        cwd: backendRoot,
        env: {
          ...process.env,
          PYTHONPATH: backendRoot,
          SPREAD_SYSTEM_DATA_DIR: runtimeDataDir
        },
        stdio: ["ignore", "pipe", "pipe"]
      }
    );

    backendProcess.on("error", (error) => {
      logStream.write(`\nbackend spawn error: ${error?.message || "unknown"}\n`);
    });
  }
  backendProcess.stdout.pipe(logStream);
  backendProcess.stderr.pipe(logStream);
  backendProcess.on("exit", (code) => {
    logStream.write(`\nbackend exited with code ${code}\n`);
    backendProcess = null;
  });
  return true;
}

function appendUpdaterLog(message) {
  if (!updaterLogPath) return;
  try {
    fs.appendFileSync(updaterLogPath, `[${new Date().toISOString()}] ${message}\n`, "utf-8");
  } catch (_e) {
    // Ignore update logging failures.
  }
}

function setupAutoUpdater() {
  if (!isPackaged || !autoUpdater) return;
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowPrerelease = false;

  autoUpdater.on("checking-for-update", () => appendUpdaterLog("Checking for updates..."));
  autoUpdater.on("update-available", (info) => appendUpdaterLog(`Update available: ${info?.version || "unknown"}`));
  autoUpdater.on("update-not-available", (info) => appendUpdaterLog(`No update available. Current=${app.getVersion()} Latest=${info?.version || "same"}`));
  autoUpdater.on("error", (error) => appendUpdaterLog(`Updater error: ${error?.message || String(error)}`));
  autoUpdater.on("download-progress", (progress) => {
    appendUpdaterLog(`Download progress: ${Math.round(progress?.percent || 0)}%`);
  });
  autoUpdater.on("update-downloaded", async (info) => {
    appendUpdaterLog(`Update downloaded: ${info?.version || "unknown"}`);
    if (!mainWindow) {
      autoUpdater.quitAndInstall();
      return;
    }
    const result = await dialog.showMessageBox(mainWindow, {
      type: "info",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
      title: "Update ready",
      message: `Version ${info?.version || "new"} is ready to install.`,
      detail: "The app will restart and apply the update."
    });
    if (result.response === 0) autoUpdater.quitAndInstall();
  });

  autoUpdater.checkForUpdates().catch((error) => appendUpdaterLog(`Initial check failed: ${error?.message || String(error)}`));
  updaterInterval = setInterval(() => {
    autoUpdater.checkForUpdates().catch((error) => appendUpdaterLog(`Periodic check failed: ${error?.message || String(error)}`));
  }, 30 * 60 * 1000);
}

async function createWindow() {
  const started = startBackend();
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 980,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#07111f",
    title: "Spread System v3",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  const rendererLogPath = path.join(runtimeLogsDir, "renderer.log");
  updaterLogPath = path.join(runtimeLogsDir, "updater.log");
  appendUpdaterLog(`App version ${app.getVersion()} started`);
  const rendererLog = fs.createWriteStream(rendererLogPath, { flags: "a" });
  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    rendererLog.write(`did-fail-load code=${errorCode} desc=${errorDescription} url=${validatedURL}\n`);
  });
  mainWindow.webContents.on("did-finish-load", async () => {
    try {
      const probe = await mainWindow.webContents.executeJavaScript(
        `(() => ({
          url: location.href,
          title: document.title,
          rootChars: (document.getElementById("root")?.innerText || "").length,
          bodyChars: (document.body?.innerText || "").length
        }))()`,
        true
      );
      rendererLog.write(`did-finish-load ${JSON.stringify(probe)}\n`);
    } catch (error) {
      rendererLog.write(`did-finish-load probe failed: ${error?.message || "unknown"}\n`);
    }
  });
  mainWindow.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    rendererLog.write(`console level=${level} ${sourceId}:${line} ${message}\n`);
  });
  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    rendererLog.write(`render-process-gone reason=${details.reason} exitCode=${details.exitCode}\n`);
  });
  if (!started) {
    // startBackend() already emitted user-facing error details.
    return;
  }
  const backendReady = await waitForBackend();
  if (!backendReady) {
    dialog.showErrorBox("Backend failed to start", `The local backend did not become ready. Check logs at ${backendLogPath || "backend.log"}.`);
  }

  if (backendReady) {
    // Inject stored secrets before starting the trading engine loops.
    try {
      await injectCredentialsFromKeychain();
    } catch (_e) {
      // Non-fatal: live mode remains blocked until credentials are injected via wizard.
    }
  }

  // Ensure the trading engine loops are running (websocket live stream depends on it).
  if (backendReady) {
    const engineStarted = await new Promise((resolve) => {
      const req = http.request(
        {
          hostname: "127.0.0.1",
          port: 8000,
          path: "/start",
          method: "POST",
          timeout: 5000
        },
        (res) => {
          if ((res.statusCode || 500) >= 400) {
            resolve(false);
            return;
          }
          // Drain response then resolve.
          res.on("data", () => {});
          res.on("end", () => resolve(true));
        }
      );
      req.on("error", () => resolve(false));
      req.on("timeout", () => {
        req.destroy();
        resolve(false);
      });
      req.end();
    });
    if (!engineStarted) {
      dialog.showErrorBox("Engine failed to start", "The backend started, but the trading engine did not start. Check backend logs.");
    }
  }
  try {
    if (isPackaged) await mainWindow.loadFile(frontendIndex);
    else await mainWindow.loadURL(frontendIndex);
    setupAutoUpdater();
  } catch (error) {
    rendererLog.write(`load frontend failed: ${error?.message || "unknown"}\n`);
    dialog.showErrorBox("Frontend failed to load", `The desktop UI failed to load. Check logs at ${rendererLogPath}.`);
  }
}

ipcMain.handle("open-backend-log", async () => {
  if (!backendLogPath) return false;
  await shell.openPath(backendLogPath);
  return true;
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
app.on("before-quit", () => {
  if (updaterInterval) {
    clearInterval(updaterInterval);
    updaterInterval = null;
  }
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
