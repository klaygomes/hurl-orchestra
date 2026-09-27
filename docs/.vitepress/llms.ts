import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { DefaultTheme } from 'vitepress';

interface Page {
  section: string;
  title: string;
  link: string;
  summary: string;
  body: string;
}

const SNIPPET = /^([ \t]*)<<<[ \t]+@\/(\S+?)(?:\{(\w+)\})?[ \t]*$/gm;
const INCLUDE = /^<!--@include:\s*(\S+?)\s*-->$/gm;

function inline(source: string, file: string, srcDir: string): string {
  return source
    .replace(SNIPPET, (_, indent: string, path: string, lang?: string) => {
      const code = readFileSync(join(srcDir, path), 'utf8').trimEnd();
      const fence = [`\`\`\`${lang ?? ''}`, ...code.split('\n'), '```'];
      return fence.map((line) => (line ? indent + line : '')).join('\n');
    })
    .replace(INCLUDE, (_, path: string) => readFileSync(join(dirname(file), path), 'utf8').trimEnd())
    .replace(/<code v-pre>(.*?)<\/code>/g, '`$1`')
    .replace(/^<[A-Z]\w*[^>]*\/>\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n');
}

function summary(body: string): string {
  const paragraph = body
    .split('\n\n')
    .map((block) => block.trim())
    .find((block) => block && !block.startsWith('#') && !block.startsWith('<') && !block.startsWith('```'));
  return (paragraph ?? '').replace(/\s+/g, ' ');
}

function pages(sidebar: DefaultTheme.SidebarItem[], srcDir: string): Page[] {
  const seen = new Set<string>();
  return sidebar.flatMap((group) =>
    (group.items ?? []).flatMap((item) => {
      if (!item.link || seen.has(item.link)) return [];
      seen.add(item.link);
      const name = item.link.endsWith('/') ? `${item.link}index` : item.link;
      const file = join(srcDir, `${name}.md`);
      const body = inline(readFileSync(file, 'utf8'), file, srcDir).trim();
      const title = body.match(/^# (.+)$/m)?.[1] ?? item.text ?? name;
      return [{ section: group.text ?? '', title, link: item.link, summary: summary(body), body }];
    }),
  );
}

export function writeLlms(options: {
  outDir: string;
  srcDir: string;
  site: string;
  title: string;
  description: string;
  sidebar: DefaultTheme.SidebarItem[];
}): void {
  const all = pages(options.sidebar, options.srcDir);
  const index = [`# ${options.title}`, '', `> ${options.description}`];
  let section = '';
  for (const page of all) {
    if (page.section !== section) {
      section = page.section;
      index.push('', `## ${section}`, '');
    }
    index.push(`- [${page.title}](${options.site}${page.link}): ${page.summary}`);
  }
  index.push('', '## Optional', '', `- [Full documentation](${options.site}/llms-full.txt): All pages in one file.`);
  writeFileSync(join(options.outDir, 'llms.txt'), `${index.join('\n')}\n`);

  const full = [`# ${options.title}`, '', `> ${options.description}`];
  for (const page of all) full.push('', '---', '', `Source: ${options.site}${page.link}`, '', page.body);
  writeFileSync(join(options.outDir, 'llms-full.txt'), `${full.join('\n')}\n`);
}
