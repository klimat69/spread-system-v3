const fs = require("fs");
const path = require("path");

const base = JSON.parse(fs.readFileSync(path.join(__dirname, "electron-builder.json"), "utf8"));
const arch = process.env.SPREAD_MAC_ARCH;

if (arch === "x64" || arch === "arm64") {
  base.mac = {
    ...base.mac,
    target: [
      { target: "zip", arch: [arch] },
      { target: "dmg", arch: [arch] }
    ]
  };
}

module.exports = base;
