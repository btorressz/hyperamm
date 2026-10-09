const { execFileSync } = require('node:child_process');
const path = require('node:path');
const cwd = path.resolve(__dirname, '..');
const compiled = path.resolve(cwd, '../work/frontend-tests');
execFileSync(process.execPath, [path.join(cwd, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2022', '--module', 'commonjs', '--moduleResolution', 'node',
  '--jsx', 'react-jsx', '--resolveJsonModule', '--esModuleInterop', '--skipLibCheck', '--strict',
  '--outDir', compiled, 'src/utils/validateTerminal.ts', 'src/utils/terminalSocket.ts', 'src/utils/terminalHistory.ts', 'src/utils/authorizationLineage.ts', 'src/utils/freshness.ts', 'src/components/AgentPanel.tsx', 'src/components/YahooObservationPanel.tsx'], { cwd, stdio: 'inherit' });
execFileSync(process.execPath, ['--test', '--test-reporter=spec', 'tests/terminal.test.cjs', 'tests/audit-lineage.test.cjs', 'tests/freshness.test.cjs', 'tests/agents.test.cjs', 'tests/yahoo.test.cjs'], {
  cwd, stdio: 'inherit', env: { ...process.env, NODE_PATH: path.join(cwd, 'node_modules'), TERMINAL_TEST_BUILD: compiled },
});
