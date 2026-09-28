<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { cue } from '../cue';
import { type Line, type Outcome, type Status, perform, shop, waves } from '../score';

const props = withDefaults(
  defineProps<{
    autoplay?: 'view' | 'cue' | 'none';
    terminal?: boolean;
    dir?: string;
  }>(),
  { autoplay: 'view', terminal: true, dir: 'tests' },
);

const nodes = shop;
const measures = waves(nodes);
const root = ref<HTMLElement>();
const sheet = ref<HTMLElement>();
const sheetWidth = ref(960);
const vertical = ref(false);
const reduced = ref(false);
const outcomes = reactive<Record<string, Outcome>>({});
const statuses = reactive<Record<string, Status>>(Object.fromEntries(nodes.map((n) => [n.id, 'idle'])));
const lines = ref<Line[]>([]);
const typed = ref('');
const activeWave = ref(0);
const exitCode = ref<number | null>(null);
const playing = ref(false);
const played = ref(false);
const inView = ref(false);
let run = 0;
let observer: IntersectionObserver | undefined;
let resize: ResizeObserver | undefined;

const command = computed(() => `hurl-orchestra ./${props.dir}`);
const changed = computed(() => Object.values(outcomes).some((o) => o !== 'pass'));

const geometry = computed(() => {
  if (vertical.value) {
    const rowH = 150;
    const top = 56;
    return {
      width: 360,
      height: top + rowH * measures.length + 16,
      node: (wave: number, slot: number) => ({ x: 40 + slot * 196, y: top + (wave - 0.5) * rowH }),
      measure: (wave: number) => ({ x: 0, y: top + (wave - 1) * rowH, w: 360, h: rowH }),
    };
  }
  const width = Math.round(Math.min(960, Math.max(680, sheetWidth.value - 16)));
  const left = 92;
  const measureW = (width - left - 20) / measures.length;
  const staffTop = 92;
  const staffH = 144;
  return {
    width,
    height: 300,
    node: (wave: number, slot: number) => ({ x: left + (wave - 0.5) * measureW, y: staffTop + slot * staffH }),
    measure: (wave: number) => ({ x: left + (wave - 1) * measureW, y: 20, w: measureW, h: 262 }),
  };
});

const pillWidth = (id: string) => id.length * 8.4 + 40;

const placed = computed(() =>
  nodes.map((node) => {
    const at = geometry.value.node(node.wave, node.slot);
    return { ...node, ...at, w: pillWidth(node.id) };
  }),
);

const byId = computed(() => Object.fromEntries(placed.value.map((n) => [n.id, n])));

const lanes = computed(() => {
  const ties = placed.value
    .flatMap((target) => target.deps.map((dep) => ({ dep, target: target.id, span: target.wave - byId.value[dep].wave })))
    .filter((tie) => tie.span > 1)
    .sort((a, b) => a.span - b.span);
  return Object.fromEntries(ties.map((tie, index) => [`${tie.dep}->${tie.target}`, index]));
});

function rail(points: [number, number][], radius = 12): string {
  let d = `M${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1];
    const [x, y] = points[i];
    const [nx, ny] = points[i + 1];
    const inLen = Math.hypot(x - px, y - py);
    const outLen = Math.hypot(nx - x, ny - y);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    const ax = x - ((x - px) / inLen) * r;
    const ay = y - ((y - py) / inLen) * r;
    const bx = x + ((nx - x) / outLen) * r;
    const by = y + ((ny - y) / outLen) * r;
    d += ` L${ax} ${ay} Q${x} ${y} ${bx} ${by}`;
  }
  const [lx, ly] = points[points.length - 1];
  return `${d} L${lx} ${ly}`;
}

const edges = computed(() =>
  placed.value.flatMap((target) =>
    target.deps.map((dep) => {
      const source = byId.value[dep];
      const span = target.wave - source.wave;
      let d: string;
      if (vertical.value) {
        const y1 = source.y + 17;
        const y2 = target.y - 17;
        if (span === 1) {
          const my = (y1 + y2) / 2;
          d = `M${source.x} ${y1} C${source.x} ${my}, ${target.x} ${my}, ${target.x} ${y2}`;
        } else {
          const lane = 300 + 18 * lanes.value[`${dep}->${target.id}`];
          const exitX = source.x + source.w / 2 - 14;
          const gapY = source.y + 17 + 22 + 8 * lanes.value[`${dep}->${target.id}`];
          d = rail([
            [exitX, source.y + 17],
            [exitX, gapY],
            [lane, gapY],
            [lane, target.y],
            [target.x + target.w / 2, target.y],
          ]);
        }
      } else {
        const x1 = source.x + source.w / 2;
        const x2 = target.x - target.w / 2;
        if (span === 1) {
          const mx = (x1 + x2) / 2;
          d = `M${x1} ${source.y} C${mx} ${source.y}, ${mx} ${target.y}, ${x2} ${target.y}`;
        } else {
          const arc = Math.min(source.y, target.y) - 30 - 26 * (span - 1);
          d = `M${source.x + 10} ${source.y - 17} C${source.x + 60} ${arc}, ${target.x - 60} ${arc}, ${target.x - 10} ${target.y - 17}`;
        }
      }
      return { id: `${dep}->${target.id}`, source: dep, target: target.id, d, tie: span > 1 };
    }),
  ),
);

const edgeState = (source: string) => {
  const status = statuses[source];
  if (status === 'pass') return 'carried';
  if (status === 'fail' || status === 'known' || status === 'skipped' || status === 'skipped-known') return 'cut';
  return 'idle';
};

const labels: Record<Status, string> = {
  idle: 'waits',
  running: 'runs',
  pass: 'passes',
  fail: 'fails',
  known: 'is a known failure',
  skipped: 'is skipped',
  'skipped-known': 'is skipped',
};

const nextOutcome: Record<Outcome, Outcome> = { pass: 'fail', fail: 'known', known: 'pass' };

const outcomeName: Record<Outcome, string> = { pass: 'pass', fail: 'fail', known: 'known failure' };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, reduced.value ? 0 : ms));

function reset() {
  for (const node of nodes) statuses[node.id] = 'idle';
  lines.value = [];
  typed.value = '';
  activeWave.value = 0;
  exitCode.value = null;
}

async function play() {
  const token = ++run;
  const alive = () => token === run;
  reset();
  playing.value = true;
  played.value = true;
  const performance = perform(nodes, outcomes, props.dir);

  for (const char of command.value) {
    typed.value += char;
    await sleep(26);
    if (!alive()) return;
  }
  await sleep(260);
  lines.value = [{ text: `Variables file: ${props.dir}/.env`, tone: 'dim' }];
  await sleep(200);

  for (const wave of measures) {
    if (!alive()) return;
    activeWave.value = wave;
    const steps = performance.steps.filter((step) => step.wave === wave);
    for (const step of steps) {
      if (step.status !== 'skipped' && step.status !== 'skipped-known') statuses[step.node] = 'running';
    }
    await sleep(steps.some((s) => statuses[s.node] === 'running') ? 720 : 280);
    for (const step of steps) {
      if (!alive()) return;
      statuses[step.node] = step.status;
      lines.value = [...lines.value, ...step.lines];
      await sleep(150);
    }
    await sleep(320);
  }

  if (!alive()) return;
  activeWave.value = 0;
  for (const line of performance.summary) {
    lines.value = [...lines.value, line];
    await sleep(160);
  }
  exitCode.value = performance.exitCode;
  playing.value = false;
}

function toggle(id: string) {
  outcomes[id] = nextOutcome[outcomes[id] ?? 'pass'];
  play();
}

function restore() {
  for (const key of Object.keys(outcomes)) delete outcomes[key];
  play();
}

function maybeStart() {
  if (played.value || !inView.value) return;
  if (props.autoplay === 'view' || (props.autoplay === 'cue' && cue.value)) play();
}

watch(cue, maybeStart);

onMounted(() => {
  reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!root.value) return;
  resize = new ResizeObserver(() => {
    vertical.value = (root.value?.clientWidth ?? 960) < 640;
    sheetWidth.value = sheet.value?.clientWidth ?? 960;
  });
  resize.observe(root.value);
  if (sheet.value) resize.observe(sheet.value);
  if (props.autoplay === 'none') return;
  observer = new IntersectionObserver(
    ([entry]) => {
      inView.value = entry.isIntersecting;
      maybeStart();
    },
    { threshold: 0.35 },
  );
  observer.observe(root.value);
});

onBeforeUnmount(() => {
  run++;
  observer?.disconnect();
  resize?.disconnect();
});
</script>

<template>
  <figure ref="root" class="score" :class="{ 'score--vertical': vertical, 'score--solo': !terminal }">
    <div class="score__grid">
    <div ref="sheet" class="score__sheet">
      <header class="score__bar">
        <span class="score__title">{{ dir }}/ <span class="score__count">{{ nodes.length }} files</span></span>
        <div class="score__actions">
          <button v-if="changed" type="button" class="score__button score__button--quiet" @click="restore">
            Pass all
          </button>
          <button type="button" class="score__button" :disabled="playing" @click="play">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" /></svg>
            {{ played ? (vertical ? 'Replay' : 'Play again') : 'Play' }}
          </button>
        </div>
      </header>

      <svg
        class="score__svg"
        :viewBox="`0 0 ${geometry.width} ${geometry.height}`"
        role="group"
        aria-label="The dependency graph of the example suite, one wave for each measure"
      >
        <g class="score__measures">
          <g v-for="wave in measures" :key="wave" :class="{ 'is-active': activeWave === wave }">
            <rect
              class="score__measure"
              :x="geometry.measure(wave).x"
              :y="geometry.measure(wave).y"
              :width="geometry.measure(wave).w"
              :height="geometry.measure(wave).h"
              rx="14"
            />
            <text
              class="score__wave"
              :x="geometry.measure(wave).x + (vertical ? 14 : geometry.measure(wave).w / 2)"
              :y="geometry.measure(wave).y + (vertical ? 22 : geometry.measure(wave).h - 10)"
              :text-anchor="vertical ? 'start' : 'middle'"
            >
              wave {{ wave }}
            </text>
          </g>
        </g>

        <g v-if="!vertical" class="score__staff" aria-hidden="true">
          <line v-for="i in 5" :key="i" x1="24" :x2="geometry.width - 16" :y1="92 + (i - 1) * 36" :y2="92 + (i - 1) * 36" />
          <line
            v-for="wave in measures.length + 1"
            :key="`bar-${wave}`"
            class="score__barline"
            :x1="geometry.measure(1).x + (wave - 1) * geometry.measure(1).w"
            :x2="geometry.measure(1).x + (wave - 1) * geometry.measure(1).w"
            y1="92"
            y2="236"
          />
          <text class="score__clef" x="36" y="186">𝄞</text>
        </g>

        <g class="score__edges" aria-hidden="true">
          <path
            v-for="edge in edges"
            :key="edge.id"
            :d="edge.d"
            pathLength="1"
            class="score__edge"
            :class="[`is-${edgeState(edge.source)}`, { 'is-tie': edge.tie }]"
          />
        </g>

        <g
          v-for="node in placed"
          :key="node.id"
          class="score__note"
          :class="`is-${statuses[node.id]}`"
          :transform="`translate(${node.x} ${node.y})`"
          role="button"
          tabindex="0"
          :aria-label="`${node.id} ${labels[statuses[node.id]]}. Its planned outcome is ${outcomeName[outcomes[node.id] ?? 'pass']}. Press to change it.`"
          @click="toggle(node.id)"
          @keydown.enter.prevent="toggle(node.id)"
          @keydown.space.prevent="toggle(node.id)"
        >
          <circle class="score__halo" r="30" />
          <rect class="score__pill" :x="-node.w / 2" y="-17" :width="node.w" height="34" rx="17" />
          <circle class="score__dot" :cx="-node.w / 2 + 17" cy="0" r="5" />
          <text class="score__label" :x="-node.w / 2 + 29" y="5">{{ node.id }}</text>
          <circle
            v-if="(outcomes[node.id] ?? 'pass') !== 'pass'"
            class="score__flag"
            :class="`is-${outcomes[node.id]}`"
            :cx="node.w / 2 - 4"
            cy="-15"
            r="6"
          />
        </g>
      </svg>

      <figcaption class="score__legend">
        <span class="score__key is-pass">passes</span>
        <span class="score__key is-fail">fails</span>
        <span class="score__key is-known">known failure</span>
        <span class="score__key is-skipped">skipped</span>
        <span class="score__hint">Tap or click a box to change its result.</span>
      </figcaption>
    </div>

    <div v-if="terminal" class="score__terminal">
      <div class="score__chrome" aria-hidden="true"><i /><i /><i /><span>zsh</span></div>
      <div class="score__log" role="log" aria-live="polite">
        <div class="score__line is-prompt">
          <span class="score__ps1">$</span> {{ typed }}<span v-if="!lines.length" class="score__cursor" />
        </div>
        <div v-for="(line, i) in lines" :key="i" class="score__line" :class="`is-${line.tone}`">{{ line.text }}</div>
        <div v-if="exitCode !== null" class="score__line is-prompt">
          <span class="score__ps1">$</span> echo $?
        </div>
        <div v-if="exitCode !== null" class="score__line" :class="exitCode ? 'is-fail' : 'is-ok'">{{ exitCode }}</div>
        <div v-if="exitCode !== null" class="score__line is-prompt">
          <span class="score__ps1">$</span> <span class="score__cursor" />
        </div>
      </div>
    </div>
    </div>
  </figure>
</template>
