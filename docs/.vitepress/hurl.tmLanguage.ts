import type { LanguageRegistration } from 'shiki';

export const hurl: LanguageRegistration = {
  name: 'hurl',
  scopeName: 'source.hurl',
  embeddedLangs: ['yaml', 'json'],
  patterns: [
    { include: '#frontmatter' },
    { include: '#comment' },
    { include: '#request' },
    { include: '#response' },
    { include: '#section' },
    { include: '#json' },
    { include: '#line' },
  ],
  repository: {
    frontmatter: {
      begin: '\\A---\\s*$',
      end: '^---\\s*$',
      beginCaptures: { 0: { name: 'punctuation.definition.frontmatter.hurl' } },
      endCaptures: { 0: { name: 'punctuation.definition.frontmatter.hurl' } },
      contentName: 'meta.embedded.block.yaml',
      patterns: [{ include: 'source.yaml' }],
    },
    comment: {
      match: '#.*$',
      name: 'comment.line.number-sign.hurl',
    },
    request: {
      match: '^(GET|HEAD|POST|PUT|DELETE|CONNECT|OPTIONS|TRACE|PATCH)\\s+(.*)$',
      captures: {
        1: { name: 'keyword.control.method.hurl' },
        2: { name: 'string.unquoted.url.hurl', patterns: [{ include: '#template' }] },
      },
    },
    response: {
      match: '^(HTTP(?:/[\\d.]+)?)\\s+(\\d{3}|\\*)',
      captures: {
        1: { name: 'keyword.other.http.hurl' },
        2: { name: 'constant.numeric.status.hurl' },
      },
    },
    section: {
      match: '^\\[(\\w+)\\]\\s*$',
      name: 'entity.name.section.hurl',
    },
    json: {
      begin: '^(?=\\s*[{\\[]\\s*("|$|\\{|\\[|\\d))',
      end: '^(?=\\s*$|HTTP|[A-Z]+\\s)',
      patterns: [{ include: '#template' }, { include: 'source.json' }],
    },
    line: {
      match: '^([\\w.-]+)(:)\\s*(.*)$',
      captures: {
        1: { name: 'variable.other.key.hurl' },
        2: { name: 'punctuation.separator.key-value.hurl' },
        3: { patterns: [{ include: '#query' }] },
      },
    },
    query: {
      patterns: [
        { include: '#template' },
        {
          match: '\\b(jsonpath|xpath|header|cookie|body|status|regex|duration|count|contains|startsWith|endsWith|matches|exists|isEmpty)\\b',
          name: 'support.function.query.hurl',
        },
        { match: '==|!=|>=|<=|>|<', name: 'keyword.operator.comparison.hurl' },
        { match: '"(?:[^"\\\\]|\\\\.)*"', name: 'string.quoted.double.hurl' },
        { match: '\\b\\d+(?:\\.\\d+)?\\b', name: 'constant.numeric.hurl' },
      ],
    },
    template: {
      match: '(\\{\\{)\\s*([\\w-]+)\\s*(\\}\\})',
      captures: {
        1: { name: 'punctuation.definition.template.begin.hurl' },
        2: { name: 'variable.parameter.template.hurl' },
        3: { name: 'punctuation.definition.template.end.hurl' },
      },
    },
  },
};
