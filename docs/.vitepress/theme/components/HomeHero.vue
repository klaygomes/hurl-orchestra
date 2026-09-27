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
const copied = ref(false);
const calm = ref(false);
let frame = 0;
let watcher = 0;

const still = withBase('/mascot/conductor.webp');
const install = 'pip install hurl-orchestra';

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

async function copy() {
  try {
    await navigator.clipboard.writeText(install);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1600);
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
  const firstVisit = !readSeen();
  writeSeen();

  if (!frugal) source.value = withBase(apple ? '/mascot/conductor.mp4' : '/mascot/conductor.webm');
  if (calm.value || frugal || !firstVisit) return giveCue();

  const path = underline.value;
  if (!path) return playWhenReady();
  path.addEventListener('animationend', playWhenReady, { once: true });
});

onBeforeUnmount(() => {
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
        and for your AI assistant.
      </p>
      <div class="hh__actions rise" style="--d: 4">
        <a class="hh__button hh__button--brand" :href="withBase('/guide/getting-started')">Get started</a>
        <a class="hh__button" :href="withBase('/how-to/work-with-ai-agents')">Use it with your AI assistant</a>
      </div>
      <button type="button" class="hh__install rise" style="--d: 5" :aria-label="`Copy: ${install}`" @click="copy">
        <span class="hh__ps1" aria-hidden="true">$</span>
        <code>{{ install }}</code>
        <span class="hh__copy-state" aria-live="polite">{{ copied ? 'Copied' : 'Copy' }}</span>
      </button>
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
