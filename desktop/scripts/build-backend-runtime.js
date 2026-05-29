const { spawnSync } = require("child_process");
const path = require("path");

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: "inherit",
    env: process.env
  });
  return result.status === 0;
}

function resolvePython() {
  const preferred = process.env.SPREAD_PYTHON;
  if (preferred) return preferred;

  const desktopRoot = path.resolve(__dirname, "..");
  const candidates = process.platform === "win32" ? ["py", "python"] : ["python3", "python"];

  for (const candidate of candidates) {
    const args = candidate === "py" ? ["-3", "--version"] : ["--version"];
    const ok = run(candidate, args, desktopRoot);
    if (ok) return candidate;
  }
  return null;
}

function main() {
  const desktopRoot = path.resolve(__dirname, "..");
  const python = resolvePython();
  if (!python) {
    console.error("[build-backend-runtime] Python interpreter not found.");
    process.exit(1);
  }

  const pyArgs = (subArgs) => (python === "py" ? ["-3", ...subArgs] : subArgs);

  if (!run(python, pyArgs(["-m", "pip", "install", "-r", "../requirements.txt"]), desktopRoot)) process.exit(1);
  if (!run(python, pyArgs(["-m", "pip", "install", "pyinstaller"]), desktopRoot)) process.exit(1);
  if (!run(python, pyArgs(["-c", "import shutil; shutil.rmtree('backend-runtime', ignore_errors=True)"]), desktopRoot)) process.exit(1);
  if (
    !run(
      python,
      pyArgs([
        "-m",
        "PyInstaller",
        "../backend/app/server_entrypoint.py",
        "--paths",
        "../backend",
        "--hidden-import",
        "app.main",
        "--hidden-import",
        "certifi",
        "--collect-data",
        "certifi",
        "--onefile",
        "--name",
        "spread-backend",
        "--distpath",
        "./backend-runtime",
        "--workpath",
        "./pyinstaller-work",
        "--specpath",
        "./pyinstaller-spec",
        "--clean"
      ]),
      desktopRoot
    )
  ) {
    process.exit(1);
  }
}

main();
