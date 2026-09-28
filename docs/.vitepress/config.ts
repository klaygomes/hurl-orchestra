import { type DefaultTheme, defineConfig } from 'vitepress';
import { bundledLanguages } from 'shiki';
import { hurl } from './hurl.tmLanguage';
import { writeLlms } from './llms';

const guide: DefaultTheme.SidebarItem[] = [
  {
    text: 'Get started',
    items: [
      { text: 'Install and run', link: '/guide/getting-started' },
      { text: 'Work with AI agents', link: '/how-to/work-with-ai-agents' },
    ],
  },
  {
    text: 'Concepts',
    items: [
      { text: 'The graph', link: '/concepts/graph' },
      { text: 'Variables', link: '/concepts/variables' },
      { text: 'Aliases', link: '/concepts/aliases' },
      { text: 'Failures and skips', link: '/concepts/failures' },
      { text: 'Reports', link: '/concepts/reports' },
    ],
  },
  {
    text: 'How-to',
    items: [
      { text: 'Run specific files', link: '/how-to/run-specific-files' },
      { text: 'Preview the plan', link: '/how-to/preview-the-plan' },
      { text: 'Give flags to Hurl', link: '/how-to/pass-hurl-flags' },
      { text: 'Order the nodes in a wave', link: '/how-to/order-a-wave' },
      { text: 'Retry on back pressure', link: '/how-to/retry-on-back-pressure' },
      { text: 'Tolerate a known failure', link: '/how-to/tolerate-a-known-failure' },
      { text: 'Report in GitHub Actions', link: '/how-to/report-in-github-actions' },
      { text: 'Draw the graph', link: '/how-to/draw-the-graph' },
    ],
  },
  {
    text: 'Reference',
    items: [
      { text: 'Overview', link: '/reference/' },
      { text: 'Command line', link: '/reference/cli' },
      { text: 'Frontmatter', link: '/reference/frontmatter' },
      { text: 'Console output', link: '/reference/console-output' },
      { text: 'CTRF report', link: '/reference/ctrf' },
    ],
  },
  {
    text: 'Troubleshooting',
    items: [{ text: 'Problems and solutions', link: '/troubleshooting' }],
  },
];

const site = 'https://www.estacouveflor.com/hurl-orchestra';
const description =
  'AI first API automation testing: write each step of an API test as a small text file, and run them in the right order.';

export default defineConfig({
  title: 'hurl-orchestra',
  description,
  base: '/hurl-orchestra/',
  lang: 'en-US',
  head: [
    ['meta', { name: 'theme-color', content: '#480f7b' }],
    [
      'script',
      {},
      "try{if(!localStorage.getItem('hurl-orchestra-intro-seen'))document.documentElement.classList.add('ho-intro')}catch(e){document.documentElement.classList.add('ho-intro')}",
    ],
    ['link', { rel: 'icon', type: 'image/png', href: '/hurl-orchestra/favicon.png' }],
    ['meta', { property: 'og:image', content: 'https://www.estacouveflor.com/hurl-orchestra/og.jpg' }],
  ],
  cleanUrls: true,
  srcExclude: ['**/*.generated.md', 'snippets/**'],
  lastUpdated: true,
  buildEnd({ outDir, srcDir }) {
    writeLlms({ outDir, srcDir, site, title: 'hurl-orchestra', description, sidebar: guide });
  },
  markdown: {
    languages: [bundledLanguages.yaml, bundledLanguages.json, hurl],
  },
  themeConfig: {
    logo: { src: '/logo.webp', alt: '' },
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'How-to', link: '/how-to/run-specific-files' },
      { text: 'AI agents', link: '/how-to/work-with-ai-agents' },
      { text: 'Reference', link: '/reference/' },
      { text: 'PyPI', link: 'https://pypi.org/project/hurl-orchestra/' },
      { text: 'Blog', link: 'https://www.estacouveflor.com', target: '_self' },
    ],
    sidebar: { '/': guide },
    socialLinks: [{ icon: 'github', link: 'https://github.com/klaygomes/hurl-orchestra' }],
    search: { provider: 'local' },
    editLink: {
      pattern: 'https://github.com/klaygomes/hurl-orchestra/edit/main/docs/:path',
    },
    footer: {
      message: 'MIT licence. Made at <a href="https://www.estacouveflor.com">Esta couve flor</a>.',
    },
  },
});
