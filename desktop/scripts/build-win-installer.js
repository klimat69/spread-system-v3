const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", env: process.env });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const root = path.resolve(__dirname, "../..");
const desktop = path.resolve(__dirname, "..");
const runtimeBinary = path.join(desktop, "backend-runtime", "spread-backend");
const runtimeBackup = path.join(desktop, "spread-backend.macos.bak");

run("npm", ["run", "build"], path.join(root, "frontend"));
run("node", ["./scripts/prepare-windows-python-embed.js"], desktop);

if (fs.existsSync(runtimeBinary)) {
  fs.renameSync(runtimeBinary, runtimeBackup);
}

try {
  run("npx", ["electron-builder", "--win", "--config", "../installer/electron-builder.json"], desktop);
} finally {
  if (fs.existsSync(runtimeBackup)) {
    if (fs.existsSync(runtimeBinary)) fs.unlinkSync(runtimeBinary);
    fs.renameSync(runtimeBackup, runtimeBinary);
  }
}

console.log("[build-win-installer] Done: installer/dist/spread-system-v3-setup.exe");
