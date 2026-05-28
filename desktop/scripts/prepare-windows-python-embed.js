const { spawnSync } = require("child_process");
const fs = require("fs");
const https = require("https");
const path = require("path");

const PYTHON_VERSION = "3.12.7";
const ZIP_NAME = `python-${PYTHON_VERSION}-embed-amd64.zip`;
const URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/${ZIP_NAME}`;
const OUT_DIR = path.resolve(__dirname, "..", "windows-python-embed");

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https
      .get(url, (response) => {
        if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          file.close();
          fs.unlinkSync(dest);
          download(response.headers.location, dest).then(resolve).catch(reject);
          return;
        }
        if (response.statusCode !== 200) {
          reject(new Error(`Download failed: ${response.statusCode} ${url}`));
          return;
        }
        response.pipe(file);
        file.on("finish", () => file.close(() => resolve(dest)));
      })
      .on("error", reject);
  });
}

function patchPth() {
  const files = fs.readdirSync(OUT_DIR).filter((name) => name.endsWith("._pth"));
  if (!files.length) throw new Error("python embed ._pth file not found");
  const pthPath = path.join(OUT_DIR, files[0]);
  const lines = fs
    .readFileSync(pthPath, "utf-8")
    .split(/\r?\n/)
    .filter((line) => line.trim() && !line.startsWith("#") && line !== "import site");
  if (!lines.includes("Lib\\site-packages")) lines.push("Lib\\site-packages");
  lines.push("import site");
  fs.writeFileSync(pthPath, `${lines.join("\r\n")}\r\n`, "utf-8");
  fs.mkdirSync(path.join(OUT_DIR, "Lib", "site-packages"), { recursive: true });
}

async function main() {
  const zipPath = path.join(OUT_DIR, ZIP_NAME);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  if (!fs.existsSync(path.join(OUT_DIR, "python.exe"))) {
    console.log(`[prepare-windows-python-embed] Downloading ${URL}`);
    await download(URL, zipPath);
    const unzip = spawnSync("unzip", ["-o", zipPath, "-d", OUT_DIR], { stdio: "inherit" });
    if (unzip.status !== 0) process.exit(unzip.status ?? 1);
  }
  patchPth();

  const getPip = path.join(OUT_DIR, "get-pip.py");
  if (!fs.existsSync(getPip)) {
    await download("https://bootstrap.pypa.io/get-pip.py", getPip);
  }
  console.log(`[prepare-windows-python-embed] Ready at ${OUT_DIR}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
