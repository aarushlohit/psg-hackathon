# OOP Backend Blueprint

## Core classes

### DevHubApp
Responsibilities:
- initialize shell
- load router
- keep current module context
- run main loop

Methods:
- run()
- render_home()
- switch_module(name)

### ModuleRouter
Responsibilities:
- registry of modules
- command dispatch

Methods:
- register(module)
- dispatch(raw_input)
- get_module(name)

### BaseModule
Abstract module contract.

Properties:
- name
- prompt_label

Methods:
- help()
- handle(command: str)
- enter()
- exit()

## CLARA classes

### ClaraModule(BaseModule)
Handles CLI mode and user commands.

### ChatServer
Socket server for rooms/messages.

### ChatClient
Client-side network operations.

### MessageStore
Temporary/persistent message storage.

## AARU classes

### AaruModule(BaseModule)

### GitService
Encapsulates subprocess git commands.

### GitResult
Structured return type for commands.

## MEMO classes

### MemoModule(BaseModule)

### MemoRepository
SQLite CRUD for tasks and notes.

### Task
- id
- title
- status
- priority
- created_at

### Note
- id
- title
- content
- created_at

## SECURE classes

### SecureModule(BaseModule)

### SecurityOrchestrator
Runs scanners and merges results.

### BanditScanner
### PipAuditScanner
### SecretScanner
### SemgrepScanner

### SecurityFinding
- scanner
- severity
- title
- file
- line
- recommendation

## Agent launcher classes

### AgentModule(BaseModule)
Optional direct launcher mode.

### AgentLauncher
- check_available(name)
- launch(name)

## Supporting classes

### ConfigManager
Reads/writes JSON config.

### ConsoleView
Rich render helpers.

### CommandParser
Parses shell commands, flags, and arguments.
