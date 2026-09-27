<script setup lang="ts">
import ScorePlayer from './ScorePlayer.vue';
</script>

<template>
  <section id="the-score" class="hs">
    <div class="hs__intro">
      <p class="hs__eyebrow">Try it</p>
      <h2 class="hs__title">Watch a test run, step by step.</h2>
      <p class="hs__text">
        Each box is one test file. A step starts only when the steps before it pass, and steps that do not depend on
        each other run at the same time. Click a box to make it fail, then see which steps stop and which continue.
      </p>
    </div>
    <ScorePlayer autoplay="cue" />
  </section>
</template>
