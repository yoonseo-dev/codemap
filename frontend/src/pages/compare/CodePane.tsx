import Editor, { type BeforeMount, type OnMount } from '@monaco-editor/react'
import { useEffect, useRef } from 'react'
import type { LineRange, SourceCode } from '../../api'
import { ymd } from '../../lib/labels'
import styles from './ComparePage.module.css'

type MonacoEditor = Parameters<OnMount>[0]

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Monaco 테마를 디자인 토큰에서 만든다 */
const defineTheme: BeforeMount = (monaco) => {
  const hex = (v: string) => cssVar(v).replace('#', '')
  monaco.editor.defineTheme('codemap', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: '', foreground: hex('--color-text-primary') },
      { token: 'keyword', foreground: hex('--color-text-muted') },
      { token: 'string', foreground: hex('--color-map-history') },
      { token: 'comment', foreground: hex('--color-text-muted') },
      { token: 'number', foreground: hex('--color-text-primary') },
    ],
    colors: {
      'editor.background': cssVar('--color-bg-canvas'),
      'editor.foreground': cssVar('--color-text-primary'),
      'editorLineNumber.foreground': cssVar('--color-text-muted'),
      'editorLineNumber.activeForeground': cssVar('--color-text-secondary'),
      'editor.lineHighlightBackground': cssVar('--color-bg-canvas'),
      'editor.selectionBackground': cssVar('--color-line-strong'),
      'editorCursor.foreground': cssVar('--color-text-primary'),
      'scrollbarSlider.background': cssVar('--color-line-subtle'),
    },
  })
}

interface Props {
  source: SourceCode
  /** 파일 기준 줄 번호로 강조할 범위 */
  highlight: LineRange[]
}

export function CodePane({ source, highlight }: Props) {
  const editorRef = useRef<MonacoEditor | null>(null)
  const decorations = useRef<{ clear(): void } | null>(null)
  const offset = source.lines[0] - 1

  const decorate = () => {
    const ed = editorRef.current
    if (!ed) return
    decorations.current?.clear()
    decorations.current = ed.createDecorationsCollection(highlight.map(([s, e]) => ({
      range: { startLineNumber: s - offset, startColumn: 1, endLineNumber: e - offset, endColumn: 1 },
      options: { isWholeLine: true, className: 'codemap-similar-line', linesDecorationsClassName: 'codemap-similar-gutter' },
    })))
  }

  useEffect(decorate, [highlight, offset])

  return (
    <section className={styles.pane} aria-label={`${source.path} 소스`}>
      <header className={styles.fileHeader}>
        <p><span className="mono">{source.path}</span> <span className={styles.lines}>{source.lines[0]}~{source.lines[1]}행</span></p>
        <p className={styles.fileMeta}>{source.changeCount}번 수정, 마지막 수정 {ymd(source.lastModified)}</p>
      </header>
      <div className={styles.editor}>
        <Editor
          value={source.code}
          language={source.language}
          theme="codemap"
          beforeMount={defineTheme}
          onMount={(ed) => { editorRef.current = ed; decorate() }}
          loading={<p className={styles.editorLoading}>코드를 불러오는 중</p>}
          options={{
            readOnly: true,
            domReadOnly: true,
            minimap: { enabled: false },
            lineNumbers: (n) => String(n + offset),
            fontFamily: cssVar('--font-mono'),
            fontSize: 13,
            lineHeight: 22,
            scrollBeyondLastLine: false,
            renderLineHighlight: 'none',
            padding: { top: 16 },
            overviewRulerLanes: 0,
            folding: false,
            contextmenu: false,
            guides: { indentation: false },
          }}
        />
      </div>
    </section>
  )
}
