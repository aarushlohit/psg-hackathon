# Engineering Principles

## 1. Build demo-first
Prioritize visible, working user flows over perfect completeness.

## 2. Modular by default
Each module must be independently testable and replaceable.

## 3. Graceful degradation
If semgrep, claude, or codex are not installed, show a helpful message instead of crashing.

## 4. Simple commands
Commands should be easy to remember and demo on stage.

## 5. Local-first
The MVP should work without cloud dependencies except optional external AI tools.

## 6. Honest scope
Security scanning is wrapper-based in MVP; do not pretend it is a full enterprise scanner.

## 7. Fast feedback
Every command should print clear success/failure output.

## 8. Consistent UX
All modules should follow similar command patterns.

## 9. Keep state minimal
Use SQLite/JSON instead of overengineering.

## 10. Build for extension
Structure code so future modules or plugins can be added.
