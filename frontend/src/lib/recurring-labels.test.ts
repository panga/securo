import { describe, expect, it } from 'vitest'
import { autoGenerateHelpKey } from './recurring-labels'

describe('autoGenerateHelpKey', () => {
  it('uses the ahead copy when RECURRING_GENERATE_AHEAD is on', () => {
    expect(autoGenerateHelpKey(true)).toBe('recurring.autoGenerateHelpAhead')
  })

  it('uses the plain copy when RECURRING_GENERATE_AHEAD is off', () => {
    expect(autoGenerateHelpKey(false)).toBe('recurring.autoGenerateHelp')
  })
})
