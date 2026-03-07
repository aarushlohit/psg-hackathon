# Project Idea — DevHub

## One-line summary
DevHub is a terminal-based developer worksuite that unifies secure team chat, simplified Git workflows, a developer knowledge/task module, security scanning, and launcher integration for external AI coding agents like Claude Code and Codex.

## Problem
Developers lose time switching between too many tools:
- terminal
- Git commands
- chat apps
- notes/todo apps
- security scanners
- AI coding agents

This fragmentation slows down execution, increases mistakes, and makes team collaboration harder.

## Solution
DevHub provides a single CLI workspace where developers can switch between integrated modules without leaving the terminal.

Core modules:
- **CLARA**: secure IP-based CLI chat
- **AARU**: simplified Git command wrapper already made --published python module pip install aarushlohit-git (just pip install and use it project)
- **MEMO**: tasks, notes, snippets, bugs, ideas
- **SECURE**: local code/dependency/secret scanning
- **Claude/Codex Launchers**: open external coding agents from inside DevHub

## Why this is good for a hackathon
- High demo value
- Clear developer pain point
- Terminal UI is fast to build
- Modular MVP is possible in hours
- Extensions are obvious and impressive

## MVP scope for submission
Build only what is demo-critical:
1. Main DevHub shell
2. `/switch` routing
3. CLARA local chat demo (single machine / LAN mock)
4. AARU commands (`save`, `status`, `branch`)
5. MEMO (`task add/list`, `note add/list`)
6. SECURE (`scan` stub or basic semgrep/bandit/pip-audit wrapper)
7. `/switch claude` and `/switch codex` launcher support

## Demo story
A developer enters DevHub, chats with team in CLARA, switches to AARU to save code git simplified, stores a task in MEMO, runs SECURE to scan, then launches Claude Code or Codex from inside the same workspace.
