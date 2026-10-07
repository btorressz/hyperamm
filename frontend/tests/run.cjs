const { execFileSync } = require('node:child_process');
const path = require('node:path');
const cwd = path.resolve(__dirname, '..');
const compiled = path.resolve(cwd, '../work/frontend-tests');
execFileSync(process.execPath, [path.join(cwd, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2022', '--module', 'commonjs', '--moduleResolution', 'node',
  '--resolveJsonModule', '--esModuleInterop', '--skipLibCheck', '--strict',
  '--outDir', compiled, 'src/utils/validateTerminal.ts', 'src/utils/terminalSocket.ts'], { cwd, stdio: 'inherit' });
execFileSync(process.execPath, ['--test', 'tests/terminal.test.cjs'], {
  cwd, stdio: 'inherit', env: { ...process.env, NODE_PATH: path.join(cwd, 'node_modules'), TERMINAL_TEST_BUILD: compiled },
});
