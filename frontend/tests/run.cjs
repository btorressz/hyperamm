const { execFileSync } = require('node:child_process');
const path = require('node:path');
const cwd = path.resolve(__dirname, '..');
const compiled = path.resolve(cwd, '../work/frontend-tests');
execFileSync(process.execPath, [path.join(cwd, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2022', '--module', 'commonjs', '--moduleResolution', 'node',
  '--jsx', 'react-jsx', '--resolveJsonModule', '--esModuleInterop', '--skipLibCheck', '--strict',
  '--outDir', compiled, 'src/pages/Execution.tsx', 'src/utils/navigation.ts', 'src/utils/quoteEvidence.ts', 'src/components/Sidebar.tsx', 'src/components/Header.tsx', 'src/components/RecentExecution.tsx', 'src/utils/validateTerminal.ts', 'src/utils/terminalSocket.ts', 'src/utils/terminalHistory.ts', 'src/utils/authorizationLineage.ts', 'src/utils/freshness.ts', 'src/components/AgentPanel.tsx', 'src/components/YahooObservationPanel.tsx', 'src/components/LiquidityDistributionChart.tsx', 'src/components/EffectiveLiquidity.tsx'], { cwd, stdio: 'inherit' });
// Modern Node can report individual cases in this execution environment.
const isolationArgs = process.allowedNodeEnvironmentFlags.has('--test-isolation') ? ['--test-isolation=none'] : [];
execFileSync(process.execPath, ['--test', ...isolationArgs, '--test-reporter=spec', 'tests/order-view.test.cjs', 'tests/navigation.test.cjs', 'tests/quote-evidence.test.cjs', 'tests/terminal.test.cjs', 'tests/terminal-integrity.test.cjs', 'tests/audit-lineage.test.cjs', 'tests/freshness.test.cjs', 'tests/agents.test.cjs', 'tests/yahoo.test.cjs', 'tests/effective-liquidity.test.cjs'], {
  cwd, stdio: 'inherit', env: { ...process.env, NODE_PATH: path.join(cwd, 'node_modules'), TERMINAL_TEST_BUILD: compiled },
});
