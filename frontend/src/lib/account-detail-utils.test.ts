import { describe, expect, it } from 'vitest'

import {
  applyTransactionToBalance,
  excludeMaterializedProjections,
} from './account-detail-utils'

describe('applyTransactionToBalance', () => {
  it('does not change the balance for ignored transactions', () => {
    expect(applyTransactionToBalance(100, {
      amount: 30,
      amount_primary: null,
      is_ignored: true,
      type: 'debit',
    }, false)).toBe(100)
  })

  it('uses the selected currency amount for active transactions', () => {
    const transaction = {
      amount: 10,
      amount_primary: 50,
      is_ignored: false,
      type: 'credit' as const,
    }

    expect(applyTransactionToBalance(100, transaction, false)).toBe(110)
    expect(applyTransactionToBalance(100, transaction, true)).toBe(150)
  })
})

describe('excludeMaterializedProjections', () => {
  it('removes only the occurrence already linked and materialized on that date', () => {
    const projections = [
      { recurring_id: 'rec-1', date: '2026-08-25' },
      { recurring_id: 'rec-1', date: '2026-09-25' },
      { recurring_id: 'rec-2', date: '2026-08-25' },
    ]

    const result = excludeMaterializedProjections(projections, [
      { recurring_transaction_id: 'rec-1', date: '2026-08-25' },
      { recurring_transaction_id: null, date: '2026-09-25' },
    ])

    expect(result).toEqual([projections[1], projections[2]])
  })
})
