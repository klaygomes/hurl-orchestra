export type Outcome = 'pass' | 'fail' | 'known';

export type Status = 'idle' | 'running' | 'pass' | 'fail' | 'known' | 'skipped' | 'skipped-known';

export type Tone = 'plain' | 'ok' | 'fail' | 'known' | 'skip' | 'dim' | 'prompt';

export interface ScoreNode {
  id: string;
  wave: number;
  slot: number;
  outputs: string[];
  deps: string[];
  status?: number;
  knownFailure: { name: string; reason: string };
}

export interface Line {
  text: string;
  tone: Tone;
}

export interface Step {
  wave: number;
  node: string;
  status: Exclude<Status, 'idle' | 'running'>;
  lines: Line[];
}

export interface Performance {
  steps: Step[];
  summary: Line[];
  exitCode: number;
}

const pool = { name: 'db_pool_exhausted', reason: 'The shared test database is at its connection limit' };

export const shop: ScoreNode[] = [
  { id: 'auth', wave: 1, slot: 0.06, outputs: ['token'], deps: [], knownFailure: pool },
  { id: 'catalog', wave: 1, slot: 0.94, outputs: [], deps: [], knownFailure: pool },
  { id: 'create_cart', wave: 2, slot: 0.34, outputs: ['cart_id'], deps: ['auth'], knownFailure: pool },
  { id: 'add_item', wave: 3, slot: 0.62, outputs: [], deps: ['auth', 'create_cart'], knownFailure: pool },
  {
    id: 'checkout',
    wave: 4,
    slot: 0.44,
    outputs: [],
    deps: ['auth', 'create_cart', 'add_item'],
    knownFailure: pool,
  },
];

export function waves(nodes: ScoreNode[]): number[] {
  return [...new Set(nodes.map((node) => node.wave))].sort((a, b) => a - b);
}

function hurlError(node: ScoreNode): Line[] {
  return [
    { text: 'error: Assert status code', tone: 'fail' },
    { text: `  --> ${node.id}.hurl:6:6`, tone: 'dim' },
    { text: '   |      ^^^ actual value is <500>', tone: 'dim' },
  ];
}

export function perform(nodes: ScoreNode[], outcomes: Record<string, Outcome>, dir = 'tests'): Performance {
  const failed = new Set<string>();
  const tolerated = new Set<string>();
  const knownByName = new Map<string, string[]>();
  const shared = new Map<string, string[]>();
  const steps: Step[] = [];
  let exitCode = 0;

  for (const wave of waves(nodes)) {
    const ready = nodes.filter((node) => node.wave === wave);
    const toRun: ScoreNode[] = [];

    for (const node of ready) {
      const failedDeps = node.deps.filter((dep) => failed.has(dep)).sort();
      if (failedDeps.length) {
        failed.add(node.id);
        steps.push({
          wave,
          node: node.id,
          status: 'skipped',
          lines: [{ text: `SKIPPED: ${node.id} (failed dependency: ${failedDeps.join(', ')})`, tone: 'skip' }],
        });
        continue;
      }
      const knownDeps = node.deps.filter((dep) => tolerated.has(dep)).sort();
      if (knownDeps.length) {
        tolerated.add(node.id);
        steps.push({
          wave,
          node: node.id,
          status: 'skipped-known',
          lines: [{ text: `SKIPPED: ${node.id} (known failure upstream: ${knownDeps.join(', ')})`, tone: 'skip' }],
        });
        continue;
      }
      toRun.push(node);
    }

    for (const node of toRun) {
      const outcome = outcomes[node.id] ?? 'pass';
      if (outcome === 'fail') {
        failed.add(node.id);
        exitCode = 1;
        steps.push({
          wave,
          node: node.id,
          status: 'fail',
          lines: [{ text: `FAILED: ${node.id}`, tone: 'fail' }, ...hurlError(node)],
        });
        continue;
      }
      if (outcome === 'known') {
        tolerated.add(node.id);
        const ids = knownByName.get(node.knownFailure.name) ?? [];
        knownByName.set(node.knownFailure.name, [...ids, node.id]);
        steps.push({
          wave,
          node: node.id,
          status: 'known',
          lines: [
            {
              text: `KNOWN FAILURE: ${node.id} [${node.knownFailure.name}] ${node.knownFailure.reason}`,
              tone: 'known',
            },
            ...hurlError(node),
          ],
        });
        continue;
      }
      const injected = node.deps.flatMap((dep) => (shared.get(dep) ?? []).map((output) => `${dep}_${output}`));
      const parts = [
        injected.length ? `injected: ${injected.join(', ')}` : '',
        node.outputs.length ? `captured: ${node.outputs.join(', ')}` : '',
      ].filter(Boolean);
      if (node.outputs.length) shared.set(node.id, node.outputs);
      steps.push({
        wave,
        node: node.id,
        status: 'pass',
        lines: [{ text: `SUCCESS: ${node.id}${parts.length ? ` [${parts.join(' | ')}]` : ''}`, tone: 'ok' }],
      });
    }
  }

  const summary: Line[] = [];
  const count = [...knownByName.values()].reduce((total, ids) => total + ids.length, 0);
  if (count) {
    const groups = [...knownByName.entries()].map(([name, ids]) => `${name}: ${[...ids].sort().join(', ')}`);
    summary.push({ text: `Known failures tolerated: ${count} (${groups.join('; ')})`, tone: 'known' });
  }
  summary.push({ text: `Report saved to ${dir}/report.zip`, tone: 'dim' });
  return { steps, summary, exitCode };
}
