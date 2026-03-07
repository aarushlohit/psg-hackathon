# Features V1

## 1. DevHub Shell
- Start with `devhub`
- Show active module
- Accept commands
- Support `/help`, `/switch`, `/exit`

## 2. CLARA
- join/create room
- send message
- list peers/messages
- local/LAN prototype acceptable

## 3. AARU
- `save` → git add . + commit + optional push
- `status` → git status
- `branch <name>` → git checkout -b <name>

## 4. MEMO
- `task add <text>`
- `task list`
- `task done <id>`
- `note add`
- `note list`
- `snippet add/list` optional if time remains

## 5. SECURE
- `scan code`
- `scan deps`
- `scan secrets`
- `scan all`
- Print summarized findings
- Gracefully degrade if scanner missing

## 6. Agent Launcher
- `/switch claude`
- `/switch codex`
- Launch if installed
- Show instruction if not installed

## 7. Shared UX
- Consistent command style
- Rich panels/tables
- Helpful status/errors
