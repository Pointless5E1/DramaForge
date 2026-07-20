# DramaForge workspace instructions

## Existing development environment

- Reuse the repository virtual environment at `D:\DramaForge\.venv`.
- Run Python with `D:\DramaForge\.venv\Scripts\python.exe` directly; activation is not required.
- Do not create another virtual environment and do not recreate `.venv` automatically.
- Before Python work, validate the existing environment with:
  `D:\DramaForge\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"`
- The `.venv` is based on Python 3.11 installed under the user's AppData directory. A sandboxed Codex command may report `Access is denied` or `Unable to create process` even when the environment is healthy. Treat that as a sandbox restriction, not as evidence of a broken venv, and retry the same read-only command with escalated permission when Python execution is necessary.
- If validation still fails outside the sandbox, report the exact error and investigate it. Ask before replacing `.venv` because rebuilding may be slow and may discard locally installed packages.
- Backend dependencies are declared in `D:\DramaForge\backend\requirements.txt`. Install them only when imports or dependency checks show they are missing, or when the user explicitly requests installation.
- Reuse `D:\DramaForge\frontend\node_modules`; do not run `npm install` unless dependencies are absent/out of date or the user requests it.

## Starting the application

- The canonical launcher is `D:\DramaForge\start-dramaforge.cmd`.
- It starts the backend with the repository `.venv`, the frontend with its existing `node_modules`, and the CLI Proxy API from `D:\CLIProxyAPI`.
- For ordinary inspection, testing, and code edits, do not start the full application unless it is needed for verification.
