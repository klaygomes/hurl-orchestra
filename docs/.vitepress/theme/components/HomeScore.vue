<script setup lang="ts">
import ScorePlayer from './ScorePlayer.vue';
</script>

<template>
  <section id="the-score" class="hs">
    <div class="hs__intro">
      <p class="hs__eyebrow">The score</p>
      <h2 class="hs__title">Each wave is one measure.</h2>
      <p class="hs__text">
        A file starts when all of its <code>deps</code> are done. Files in the same wave run together. Select a note to
        make it fail, then watch which files hurl-orchestra skips and which files continue.
      </p>
    </div>
    <ScorePlayer autoplay="cue" />
  </section>
</template>
