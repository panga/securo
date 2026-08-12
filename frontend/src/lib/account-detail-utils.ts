import type { ProjectedTransaction, Transaction } from '../types'

type BalanceTransaction = Pick<
  Transaction,
  'amount' | 'amount_primary' | 'is_ignored' | 'type'
>

type MaterializedTransaction = Pick<Transaction, 'date' | 'recurring_transaction_id'>

/** Apply one transaction to a running balance using Account Detail semantics. */
export function applyTransactionToBalance(
  balance: number,
  transaction: BalanceTransaction,
  usePrimary: boolean,
): number {
  if (transaction.is_ignored) return balance

  const amount = usePrimary && transaction.amount_primary != null
    ? Number(transaction.amount_primary)
    : Number(transaction.amount)
  return balance + (transaction.type === 'credit' ? amount : -amount)
}

/**
 * Hide virtual occurrences that already have a materialized transaction.
 * The recurring link plus the effective occurrence date is authoritative;
 * description and amount can legitimately change after materialization.
 */
export function excludeMaterializedProjections<
  T extends Pick<ProjectedTransaction, 'date' | 'recurring_id'>,
>(
  projections: T[],
  transactions: MaterializedTransaction[],
): T[] {
  const materialized = new Set(
    transactions
      .filter((transaction) => transaction.recurring_transaction_id != null)
      .map((transaction) => `${transaction.recurring_transaction_id}:${transaction.date}`),
  )

  return projections.filter(
    (projection) => !materialized.has(`${projection.recurring_id}:${projection.date}`),
  )
}
