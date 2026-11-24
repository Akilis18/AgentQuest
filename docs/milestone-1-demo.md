# Reproduce the Milestone 1 demo

From an AgentQuest checkout, use the tagged code in a separate working
directory. Run these commands in PowerShell with Git, uv, and Python 3.11
available.

```powershell
git worktree add --detach ../AgentQuest-v0.1.0 v0.1.0
Set-Location ../AgentQuest-v0.1.0
uv sync --locked --python 3.11
uv run --locked uvicorn backend.main:app
```

Open [AgentQuest](http://127.0.0.1:8000/). Click **New game** for a fresh
session at `[3, 6]`, turn 0, with 3 health.

## Guard Post walkthrough

Press each movement key separately and wait for the turn counter to update.
For non-movement actions, select the action and its item or target, then click
**Execute action**. The movement sequences use WASD.

| Turns | Input | Expected result |
|---|---|---|
| 1–7 | `ddssaas` | Reach the Decoy in Storage at `[3, 9]`. |
| 8 | **Pick up** → **Decoy** | The Decoy enters your inventory. |
| 9–20 | `wddwwddwwwdd` | Reach the guard approach at `[9, 3]`. |
| 21 | `d` | The alert guard blocks movement and the attempt uses a turn. |
| 22 | **Use item** → **Decoy** → **Vault Guard** | The guard is distracted and the Decoy is consumed. |
| 23–31 | `ddddsssdd` | Reach the treasure at `[15, 6]`. |
| 32 | **Pick up** → **Vault Treasure** | The treasure enters your inventory. |
| 33–52 | `aawwwaaaaaasssaaaaaa` | Reach the exit at `[1, 6]` and win with 3 health. |

The victory display appears and gameplay controls are disabled. **Restart**
returns the same session to turn 0 with an empty inventory and action log.

## Automated verification

Leave the server running and open another PowerShell window in the tagged
worktree. Browser tests require Node.js 22+ and an installed Chromium browser.

```powershell
uv run --locked pytest -v -W error
node --test tests/browser/game.test.mjs
```

Expect **76 backend tests** and **3 browser tests** to pass. The browser suite
plays both the Guard Post and Service Tunnel routes. See the
[README](../README.md#browser-integration-tests) for browser and server
configuration.
