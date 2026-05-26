const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const path = require("path");

let mainWindow;
let backendProcess = null;
let backendLogPath = null;

const isPackaged = app.isPackaged;
const projectRoot = isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
const backendRoot = path.join(projectRoot, "backend");
const frontendIndex = isPackaged ? path.join(process.resourcesPath, "frontend", "dist", "index.html") : "http://127.0.0.1:5173";

function pythonCommand() {
  return process.env.SPREAD_PYTHON || (process.platform === "win32" ? "python" : "python3");
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

async function waitForBackend(port = 8000, attempts = 60) {
  for (let i = 0; i < attempts; i += 1) {
    if (await canConnect(port)) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function startBackend() {
  if (backendProcess) return;
  const logsDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logsDir, { recursive: true });
  backendLogPath = path.join(logsDir, "backend.log");
  const logStream = fs.createWriteStream(backendLogPath, { flags: "a" });
  backendProcess = spawn(
    pythonCommand(),
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    {
      cwd: backendRoot,
      env: {
        ...process.env,
        PYTHONPATH: backendRoot,
        SPREAD_SYSTEM_DATA_DIR: path.join(projectRoot, "data")
      },
      stdio: ["ignore", "pipe", "pipe"]
    }
  );
  backendProcess.stdout.pipe(logStream);
  backendProcess.stderr.pipe(logStream);
  backendProcess.on("exit", (code) => {
    logStream.write(`\nbackend exited with code ${code}\n`);
    backendProcess = null;
  });
}

async function createWindow() {
  startBackend();
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
  const backendReady = await waitForBackend();
  if (!backendReady) {
    dialog.showErrorBox("Backend failed to start", `The local backend did not become ready. Check logs at ${backendLogPath || "backend.log"}.`);
  }
  if (isPackaged) await mainWindow.loadFile(frontendIndex);
  else await mainWindow.loadURL(frontendIndex);
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
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
