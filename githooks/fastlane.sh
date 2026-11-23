# Sourced by pre-commit and pre-push (not a hook itself).
# Fast lane (CLAUDE.md -> Workflow): a change may go straight to main only if every path it touches
# is a Markdown doc outside .claude/ and .github/. Code, tests, references, scripts, hooks, CI,
# agents and the PR template always go through a reviewed PR.
#
# fastlane_ok "<newline-separated paths>": returns 0 if all are allowed; prints the others to stderr.
fastlane_ok() {
  bad=0
  while IFS= read -r f; do
    case "$f" in
      "") ;;
      .claude/*|.github/*) echo "  $f" >&2; bad=1 ;;
      *.md) ;;
      *) echo "  $f" >&2; bad=1 ;;
    esac
  done <<EOF
$1
EOF
  return $bad
}
