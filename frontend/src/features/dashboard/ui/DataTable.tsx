import type { ReactNode } from 'react'

export interface Column<Row> {
  header: string
  render: (row: Row) => ReactNode
  /** Right-align figures. */
  numeric?: boolean
}

interface DataTableProps<Row> {
  /** Accessible name of the scroll region and table. */
  label: string
  columns: Column<Row>[]
  rows: Row[]
  rowKey: (row: Row) => string | number
}

/** Shared table: horizontal scroll inside its own keyboard-focusable
 * region, so the page itself never scrolls sideways on a tablet. */
export function DataTable<Row>({ label, columns, rows, rowKey }: DataTableProps<Row>) {
  return (
    <div className="pd-table-wrap" tabIndex={0} role="region" aria-label={`${label} table`}>
      <table className="pd-table" aria-label={label}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.header} scope="col" className={column.numeric ? 'pd-num' : undefined}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.header} className={column.numeric ? 'pd-num' : undefined}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
