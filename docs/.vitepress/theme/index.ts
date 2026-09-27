import type { Theme } from 'vitepress';
import DefaultTheme from 'vitepress/theme';
import '@fontsource/rubik/latin-400.css';
import '@fontsource/rubik/latin-600.css';
import '@fontsource/rubik/latin-800.css';
import '@fontsource/molengo/latin-400.css';
import '@fontsource/abel/latin-400.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-600.css';
import './custom.css';
import './home.css';
import HomeHero from './components/HomeHero.vue';
import HomeScore from './components/HomeScore.vue';
import ScorePlayer from './components/ScorePlayer.vue';

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('HomeHero', HomeHero);
    app.component('HomeScore', HomeScore);
    app.component('ScorePlayer', ScorePlayer);
  },
} satisfies Theme;
