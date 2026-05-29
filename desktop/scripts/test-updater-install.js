#!/usr/bin/env node
const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const {
  findMacAppBundleInDir,
  findPendingArtifact,
  resolveMacAppBundlePath
} = require("../updater-install");

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "spread-updater-test-"));
}

const userData = tempDir();
const cacheRoot = path.join(path.dirname(userData), "Caches", "spread-system-v3-desktop-updater", "pending");
fs.mkdirSync(cacheRoot, { recursive: true });
const zipPath = path.join(cacheRoot, "spread-system-v3-arm64.zip");
fs.writeFileSync(zipPath, "fake");

const found = findPendingArtifact(userData, ".zip");
assert.strictEqual(found, zipPath, "should find pending zip in Library/Caches");

const extractRoot = tempDir();
const bundle = path.join(extractRoot, "nested", "Spread System v3.app");
fs.mkdirSync(bundle, { recursive: true });
const located = findMacAppBundleInDir(extractRoot);
assert.strictEqual(located, bundle, "should locate .app bundle recursively");

console.log("test-updater-install: OK");
