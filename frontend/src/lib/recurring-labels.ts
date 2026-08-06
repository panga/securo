/**
 * i18n keys for the auto-generate checkbox help text.
 *
 * With the RECURRING_GENERATE_AHEAD feature flag on, the help copy explains
 * that upcoming bills are pre-created as pending; otherwise it keeps the
 * legacy wording. Kept as a pure function so the flag-driven copy choice is
 * unit-testable without mounting the form.
 */
export function autoGenerateHelpKey(
  generateAhead: boolean,
): 'recurring.autoGenerateHelp' | 'recurring.autoGenerateHelpAhead' {
  return generateAhead ? 'recurring.autoGenerateHelpAhead' : 'recurring.autoGenerateHelp'
}
