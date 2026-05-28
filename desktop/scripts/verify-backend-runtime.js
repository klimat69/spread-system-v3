const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`[verify-backend-runtime] ${message}`);
  process.exit(1);
}

const desktopRoot = path.resolve(__dirname, "..");
const binaryName = process.platform === "win32" ? "spread-backend.exe" : "spread-backend";
const binaryPath = path.join(desktopRoot, "backend-runtime", binaryName);

if (!fs.existsSync(binaryPath)) {
  fail(`Missing bundled backend binary at ${binaryPath}`);
}

const stat = fs.statSync(binaryPath);
if (!stat.isFile()) {
  fail(`Expected file but found something else: ${binaryPath}`);
}

if (process.platform !== "win32") {
  const executableBit = stat.mode & 0o111;
  if (!executableBit) {
    fail(`Binary is not executable: ${binaryPath}`);
  }
}

console.log(`[verify-backend-runtime] OK: ${binaryPath}`);
