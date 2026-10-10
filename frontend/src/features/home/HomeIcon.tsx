const paths: Record<string, string> = {
  hmi: 'M3 4h18v13H3z M8 21h8 M12 17v4',
  warehouse: 'M2 9l10-7 10 7v13h-5V12H7v10H2z M9 16h6 M9 20h6',
  production: 'M4 14h16a4 4 0 0 1 0 8H4a4 4 0 0 1 0-8z M6 18h.01 M12 18h.01 M18 18h.01 M7 3h10v8H7z',
  engineering: 'M21 3a6 6 0 0 0-8 8L3 21l-2-2L11 9a6 6 0 0 1 8-8l-4 4 4 4z',
  qa: 'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 11l3 3 5-6',
  intelligence: 'M8 17c0-3-3-4-3-8a7 7 0 0 1 14 0c0 4-3 5-3 8z M9 20h6 M10 23h4 M12 0v-2 M2 2L0 0 M22 2l2-2',
  management: 'M8 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M16 11a3 3 0 1 0 0-6 M1 22v-4a7 7 0 0 1 14 0v4z M17 14a6 6 0 0 1 6 6v2h-5',
  reports: 'M5 2h9l5 5v15H5z M14 2v6h5 M8 12h8 M8 16h8 M8 19h5',
  settings: 'M10 2h4l1 4 3-1 3 3-2 3 3 2-1 4-4 1-1 4h-4l-1-4-4-1-1-4 3-2-2-3 3-3 3 1z M15 12a3 3 0 1 0-6 0 3 3 0 0 0 6 0',
  performance: 'M3 14h4v8H3z M10 8h4v14h-4z M17 2h4v20h-4z',
  home: 'M2 11L12 2l10 9 M5 9v13h5v-7h4v7h5V9',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14 M15 15l7 7',
  help: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20 M9 8a3 3 0 1 1 4 3l-1 2 M12 17h.01',
  notifications: 'M5 17V9a7 7 0 0 1 14 0v8l2 2H3z M10 22h4',
}
export function HomeIcon({ name }: { name: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.home} /></svg>
}
