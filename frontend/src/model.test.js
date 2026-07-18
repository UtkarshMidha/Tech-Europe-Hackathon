import test from 'node:test'
import assert from 'node:assert/strict'
import { asNumber, buildWaterfall, graphLayout } from './model.js'

test('normalises audit amounts and preserves the profit bridge', () => {
  assert.equal(asNumber('€ 248.000,00'), 248000)
  assert.equal(asNumber('(47,120.00)'), -47120)
  const bridge = buildWaterfall(
    { reported_profit: '2599841.80' },
    [{ id: 'F1', title: 'Expense', amounts: { pnl_effect: '-248000' } }],
  )
  assert.equal(bridge.adjusted, 2351841.8)
  const positions = graphLayout([{ id: 'u', type: 'user' }, { id: 'p', type: 'payment' }])
  assert.ok(positions.u.x < positions.p.x)
})
