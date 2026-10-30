import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

export default async function setup() {
  const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
  try { await fetch('http://127.0.0.1:8012/healthz'); throw new Error('Test port 8012 is already in use.'); }
  catch (error) { if (error instanceof Error && error.message.includes('already in use')) throw error; }
  // Direct spawn avoids an orphaned cmd.exe/Python tree on Windows teardown.
  const executable = resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const server = spawn(executable, ['-m', 'uvicorn', 'carbon_coach.api:app', '--host', '127.0.0.1', '--port', '8012'], {
    cwd: root, stdio: 'ignore', env: { ...process.env, STORAGE_MODE: 'memory', GATEWAY_MODE: 'mock', ALLOWED_ORIGINS: 'http://127.0.0.1:8012' },
  });
  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      if (server.exitCode !== null) throw new Error('Test API exited before becoming ready.');
      try { ready = (await fetch('http://127.0.0.1:8012/readyz')).ok; } catch { /* Startup in progress. */ }
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (!ready) throw new Error('Test API did not become ready.');
  } catch (error) { server.kill(); throw error; }
  return async () => { server.kill(); };
}
