<script setup lang="ts">
import { withBase } from 'vitepress';
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { cue } from '../cue';

const CUE_SECONDS = 3.46;
const GRACE_MS = 1500;
const SEEN_KEY = 'hurl-orchestra-intro-seen';

const hero = ref<HTMLElement>();
const video = ref<HTMLVideoElement>();
const underline = ref<SVGPathElement>();
const source = ref('');
const playing = ref(false);
const copied = ref<'' | 'command' | 'prompt'>('');
const calm = ref(false);
const returning = ref(false);
let frame = 0;
let watcher = 0;

const still = withBase('/mascot/conductor.webp');
const install = 'pip install hurl-orchestra';
const prompt = [
  'Set up end-to-end API tests for this project with hurl-orchestra.',
  '',
  '1. Read the documentation first: https://www.estacouveflor.com/hurl-orchestra/llms-full.txt',
  '2. Install Hurl (https://hurl.dev/docs/installation.html) and run: pip install hurl-orchestra',
  '3. In tests/, write one .hurl file for each step of a user flow, for example login, add to cart and pay.',
  '   Declare the steps that must pass first in `deps` and the values to share in `outputs`.',
  '4. Check the plan: hurl-orchestra --dry-run --json --env-file .env tests',
  '5. Run the tests: hurl-orchestra --env-file .env tests --report-ctrf results.json',
  '6. Read tests/results.json, fix each failure or report the API defect, and run again.',
  '',
  'Keep URLs and secrets in a .env file, for example at the project root, and never in the .hurl files.',
].join('\n');

function readSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return false;
  }
}

function writeSeen() {
  try {
    localStorage.setItem(SEEN_KEY, '1');
  } catch {}
}

function giveCue() {
  cue.value = true;
}

function watchForCue() {
  cancelAnimationFrame(watcher);
  const tick = () => {
    const clip = video.value;
    if (!clip) return;
    if (clip.currentTime >= CUE_SECONDS) return giveCue();
    if (!clip.paused && !clip.ended) watcher = requestAnimationFrame(tick);
  };
  watcher = requestAnimationFrame(tick);
}

async function play() {
  const clip = video.value;
  if (!clip || !source.value) return giveCue();
  clip.currentTime = 0;
  try {
    await clip.play();
    playing.value = true;
    watchForCue();
  } catch {
    playing.value = false;
    giveCue();
  }
}

function playWhenReady() {
  const clip = video.value;
  if (!clip) return giveCue();
  if (clip.readyState >= 4) return play();
  const timer = setTimeout(() => {
    clip.removeEventListener('canplaythrough', ready);
    giveCue();
  }, GRACE_MS);
  const ready = () => {
    clearTimeout(timer);
    play();
  };
  clip.addEventListener('canplaythrough', ready, { once: true });
}

function ended() {
  playing.value = false;
  giveCue();
}

async function copy(what: 'command' | 'prompt') {
  try {
    await navigator.clipboard.writeText(what === 'command' ? install : prompt);
    copied.value = what;
    setTimeout(() => {
      if (copied.value === what) copied.value = '';
    }, 1800);
  } catch {}
}

function tilt(event: PointerEvent) {
  const box = hero.value?.getBoundingClientRect();
  if (!box || calm.value) return;
  const x = (event.clientX - box.left) / box.width - 0.5;
  const y = (event.clientY - box.top) / box.height - 0.5;
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    hero.value?.style.setProperty('--px', x.toFixed(3));
    hero.value?.style.setProperty('--py', y.toFixed(3));
  });
}

function settle() {
  hero.value?.style.setProperty('--px', '0');
  hero.value?.style.setProperty('--py', '0');
}

onMounted(() => {
  calm.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } })
    .connection;
  const frugal = Boolean(connection?.saveData) || /2g/.test(connection?.effectiveType ?? '');
  const apple = navigator.vendor === 'Apple Computer, Inc.';
  const firstVisit = document.documentElement.classList.contains('ho-intro') && !readSeen();
  writeSeen();
  returning.value = !firstVisit;

  if (!frugal) source.value = withBase(apple ? '/mascot/conductor.mp4' : '/mascot/conductor.webm');
  if (calm.value || frugal || !firstVisit) return giveCue();

  const path = underline.value;
  if (!path) return playWhenReady();
  path.addEventListener('animationend', playWhenReady, { once: true });
});

onBeforeUnmount(() => {
  document.documentElement.classList.remove('ho-intro');
  cancelAnimationFrame(frame);
  cancelAnimationFrame(watcher);
});
</script>

<template>
  <section ref="hero" class="hh" @pointermove="tilt" @pointerleave="settle">
    <div class="hh__copy">
      <p class="hh__eyebrow rise" style="--d: 0">AI first API automation testing, on <a href="https://hurl.dev">Hurl</a></p>
      <h1 class="hh__title">
        <span class="rise-mask" style="--d: 1"><span>Test your API</span></span>
        <span class="rise-mask" style="--d: 2">
          <span>from <em class="hh__accent">login to checkout.</em></span>
        </span>
        <svg class="hh__underline" viewBox="0 0 300 24" preserveAspectRatio="none" aria-hidden="true">
          <path ref="underline" pathLength="1" d="M4 16 C 70 6, 140 22, 200 12 S 280 8, 296 14" />
        </svg>
      </h1>
      <p class="hh__lede rise" style="--d: 3">
        Write each step as a small text file: log in, add to cart, pay. hurl-orchestra runs the steps in the right
        order, passes the login token to the steps that need it and shows you which step broke. Easy to read for you
        and for your
        <mark class="hh__ai">AI assistant<svg class="hh__spark" viewBox="-16 -16 32 32" aria-hidden="true"><path d="M0 -14C2 -4 4 -2 14 0C4 2 2 4 0 14C-2 4 -4 2 -14 0C-4 -2 -2 -4 0 -14Z" /></svg></mark>.
      </p>
      <div class="hh__actions rise" style="--d: 4">
        <a class="hh__button hh__button--brand" :href="withBase('/guide/getting-started')">Get started</a>
      </div>
      <div class="hh__install rise" style="--d: 5">
        <span class="hh__cmd"><span class="hh__ps1" aria-hidden="true">$</span> <code>{{ install }}</code></span>
        <button type="button" class="hh__clipboard" :aria-label="`Copy the command: ${install}`" @click="copy('command')">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="8" y="8" width="12" height="12" rx="2.5" />
            <path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8" />
          </svg>
          {{ copied === 'command' ? 'Copied' : 'Copy' }}
        </button>
        <button
          type="button"
          class="hh__clipboard hh__clipboard--ai"
          aria-label="Copy a setup prompt for your AI assistant"
          title="Copy a setup prompt for Claude Code, Codex, Cursor or any AI assistant"
          @click="copy('prompt')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2.5c.6 4.6 2.9 6.9 7.5 7.5-4.6.6-6.9 2.9-7.5 7.5-.6-4.6-2.9-6.9-7.5-7.5 4.6-.6 6.9-2.9 7.5-7.5Z" />
            <path d="M19 15.5c.25 1.9 1.1 2.75 3 3-1.9.25-2.75 1.1-3 3-.25-1.9-1.1-2.75-3-3 1.9-.25 2.75-1.1 3-3Z" />
          </svg>
          {{ copied === 'prompt' ? 'Copied' : 'Copy for AI' }}
        </button>
        <span class="hh__sr" aria-live="polite">{{ copied ? 'Copied to the clipboard' : '' }}</span>
      </div>
    </div>

    <div class="hh__stage">
      <svg class="hh__staff" viewBox="0 0 400 200" preserveAspectRatio="none" aria-hidden="true">
        <path v-for="i in 5" :key="i" :d="`M0 ${40 + i * 24} C 120 ${20 + i * 24}, 260 ${70 + i * 24}, 400 ${44 + i * 24}`" />
      </svg>
      <div class="hh__spot" aria-hidden="true" />
      <button
        type="button"
        class="hh__conductor"
        :class="{ 'is-playing': playing }"
        aria-label="Play the conductor animation again"
        @click="play"
      >
        <span v-if="returning && source" class="hh__replay" aria-hidden="true">
          <svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z" /></svg>
          Play
        </span>
        <img class="hh__still" :src="still" alt="A cauliflower in a bow tie holds a conductor baton" width="540" height="540" />
        <video
          v-if="source"
          ref="video"
          class="hh__clip"
          :src="source"
          muted
          playsinline
          preload="auto"
          aria-hidden="true"
          width="540"
          height="540"
          @ended="ended"
          @error="ended"
        />
      </button>
    </div>
  </section>
</template>
