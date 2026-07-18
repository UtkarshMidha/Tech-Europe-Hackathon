export function asNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  if (value == null) return 0
  const negative = /^\s*\(/.test(String(value))
  let raw = String(value).replace(/[^\d.,-]/g, '')
  const comma = raw.lastIndexOf(',')
  const dot = raw.lastIndexOf('.')
  if (comma >= 0 && dot >= 0) {
    raw = comma > dot ? raw.replace(/\./g, '').replace(',', '.') : raw.replace(/,/g, '')
  } else if (comma >= 0) {
    raw = /,\d{1,2}$/.test(raw) ? raw.replace(',', '.') : raw.replace(/,/g, '')
  }
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? (negative ? -Math.abs(parsed) : parsed) : 0
}

export const money = (value, compact = false) =>
  new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'EUR',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 2,
  }).format(asNumber(value))

export function buildWaterfall(run, findings = []) {
  const reported = asNumber(run?.reported_profit)
  const items = findings
    .map((finding) => ({
      id: finding.id,
      label: finding.title,
      delta: asNumber(finding.amounts?.pnl_effect),
    }))
    .filter(({ delta }) => delta !== 0)
  return { reported, items, adjusted: reported + items.reduce((sum, item) => sum + item.delta, 0) }
}

export function graphLayout(nodes = []) {
  const layer = {
    person: 0, user: 0, employee: 0,
    permission: 1, role: 1, control: 1,
    vendor: 2, supplier: 2,
    invoice: 3, order: 3, receipt: 3, journal: 3, asset: 3,
    payment: 4, transfer: 4,
    bank: 5, account: 5, cash: 5,
  }
  const grouped = new Map()
  nodes.forEach((node, index) => {
    const column = layer[String(node.type).toLowerCase()] ?? Math.min(index, 5)
    grouped.set(column, [...(grouped.get(column) || []), node])
  })
  const positions = {}
  grouped.forEach((group, column) => group.forEach((node, index) => {
    const gap = 260 / (group.length + 1)
    positions[node.id] = { x: 76 + column * 138, y: 38 + gap * (index + 1) }
  }))
  return positions
}

export function formatLocator(locator) {
  if (!locator) return 'Locator unavailable'
  if (typeof locator === 'string') return locator
  return Object.entries(locator)
    .map(([key, value]) => `${key.replaceAll('_', ' ')} ${Array.isArray(value) ? value.join(', ') : value}`)
    .join(' · ')
}
