# Learnings

## Virual Environment

### Creating

```powershell
python -m venv .venv
```

### Activating

```powershell
.venv\Scripts\Activate.ps1
```

### Bypass powershell_Execution_Policy if executing script not allowed

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process; .venv\Scripts\Activate.ps1
```

### Exit

```powershell
exit
```

## Foreign Keys in Python SQLite3

Does not support foreign key by default you need to execute the following before each connection

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

## Setting up git

```bash

# Run the initialization command. It is recommended to explicitly set your default branch name to main
git init -b main

# 1. Stage all files in the directory
git add .

# 2. Save the snapshot with a message
git commit -m "Initial commit"

git remote add origin <PASTE_REMOTE_REPOSITORY_URL>
git push -u origin main

```
