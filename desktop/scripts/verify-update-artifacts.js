#!/usr/bin/env node
/**
 * Ensures electron-builder output matches what electron-updater expects.
 * Run after `electron-builder --mac|--win` and before `publish`.
 */
const fs = require("fs");
const path = require("path");

const dist = path.resolve(__dirname, "../../installer/dist");
const platform = (process.argv[2] || "mac").toLowerCase();

function fail(message) {
  console.error(`verify-update-artifacts: ${message}`);
  process.exit(1);
}

function assertFile(filePath) {
  if (!fs.existsSync(filePath)) {
    fail(`missing file ${path.basename(filePath)}`);
  }
  const size = fs.statSync(filePath).size;
  if (size < 1_000_000) {
    fail(`${path.basename(filePath)} is too small (${size} bytes)`);
  }
}

if (platform === "mac") {
  const ymlPath = path.join(dist, "latest-mac.yml");
  if (!fs.existsSync(ymlPath)) {
    fail("missing latest-mac.yml");
  }
  const text = fs.readFileSync(ymlPath, "utf8");
  for (const arch of ["x64", "arm64"]) {
    const zipName = `spread-system-v3-${arch}.zip`;
    if (!text.includes(zipName)) {
      fail(`latest-mac.yml must reference ${zipName} (found: ${text.slice(0, 200)}...)`);
    }
    assertFile(path.join(dist, zipName));
  }
  if (!text.includes("path:")) {
    fail("latest-mac.yml missing path field");
  }
  console.log("verify-update-artifacts: mac OK (x64 + arm64 zip, latest-mac.yml)");
  process.exit(0);
}

if (platform === "win") {
  const ymlPath = path.join(dist, "latest.yml");
  if (!fs.existsSync(ymlPath)) {
    fail("missing latest.yml");
  }
  const text = fs.readFileSync(ymlPath, "utf8");
  const exe = "spread-system-v3-setup.exe";
  if (!text.includes(exe)) {
    fail(`latest.yml must reference ${exe}`);
  }
  assertFile(path.join(dist, exe));
  console.log("verify-update-artifacts: win OK (setup exe, latest.yml)");
  process.exit(0);
}

fail(`unknown platform "${platform}" (use mac or win)`);
