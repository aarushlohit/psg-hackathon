# Agent Design

DevHub includes lightweight “agents” as orchestrators, not autonomous black boxes.

## Agent types

### 1. Router Agent
Purpose:
- Understand shell command intent
- Switch or dispatch correctly

Example:
`/switch aaru` → activates AARU module

### 2. Git Workflow Agent (AARU layer)
Purpose:
- Turn simplified commands into Git command sequences

Example:
`save "init auth"` →
- git add .
- git commit -m "init auth"

### 3. Security Orchestrator Agent
Purpose:
- Run multiple scanners
- Normalize findings
- Print a short prioritized report

### 4. Productivity Agent (MEMO helpers)
Purpose:
- Convert quick input into structured task/note records

### 5. External AI Launcher Agent
Purpose:
- Detect and launch Claude Code or Codex from inside DevHub

## Non-goals for MVP
- No fully autonomous coding agent of your own
- No hidden background processes
- No exaggerated claims of AI reasoning

## Design principle
Agents should:
- be observable
- be deterministic where possible
- print their actions
- fail safely

## Example flow
User:
`/switch codex`

Router Agent:
- validates tool
- checks installation
- launches subprocess
