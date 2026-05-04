# ASF-AutoCollector-for-CS2-or-any-other-game

A vibecoded opensource project for ASF. It aims to simplify the Collection of Items over many Accounts. I did not check if this works with multiple master Accounts.
I wont keep this updated. 
As stated, this python script can be used for any other game as well. You just got to change the AppID and ContextID numbers to the corresponding game. 
Check the Readme for a detailed installation rundown. It is advised to not change any numbers unless you understand what those are good for. 
And remember, it is vibecoded and will most likely break down, unless i did cook some good stuff with my prompts. Feel free to further improve and modify this.

Cheers

============================================================================================================================================


# AutoCollectASF

A Python script that automatically drains CS:GO tradable items from all your ArchiSteamFarm (ASF) bot accounts into a central storage account, and prints a full summary of everything that was collected.

---

## Table of Contents

1. [Requirements](#requirements)
2. [ASF Prerequisites](#asf-prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running the Script](#running-the-script)
6. [Understanding the Output](#understanding-the-output)
7. [What to Do When Bots Fail](#what-to-do-when-bots-fail)
8. [Scheduling Automatic Runs](#scheduling-automatic-runs)
9. [Troubleshooting](#troubleshooting)

---

## Requirements

- **Python 3.8 or newer**
- **`requests` library** — install with:
  ```
  pip install requests
  ```
- **ArchiSteamFarm** running locally with IPC enabled (see below)

---

## ASF Prerequisites

Before running the script, make sure the following is true in your ASF setup:

### 1. IPC must be enabled
In your `ASF.json` config, make sure this is set:
```json
"IPC": true
```
The script connects to ASF at `http://127.0.0.1:1242` by default. ASF must be running and reachable at that address before you start the script.

### 2. Each bot must have a master account configured
The `loot^` command sends items to each bot's configured master account. In each bot's `.json` config file, the `SteamUserPermissions` section must grant `Master` permission to your storage account's Steam64 ID:
```json
"SteamUserPermissions": {
    "765XXXXXXXXXXXXXX": 3 
}
```
`3` = Master permission. Replace `765XXXXXXXXXXXXXX` with your storage account's actual Steam64 ID.

### 3. Bot accounts must not have trade holds
If a bot account has a Steam Guard trade hold (e.g., newly added accounts), trades will fail. Make sure all bots have had their authenticator active for at least 7 days before running.

### 4. Config folder location
By default, the script looks for bot configs at `./config` — meaning a folder called `config` in the same directory as the script. This should already be where your ASF config folder is. If your config lives elsewhere, update `config_path` at the top of the script (see [Configuration](#configuration)).

---

## Installation

1. Place `AutoCollectScript.py` in the same directory as your ASF `config/` folder, or anywhere you prefer (just update `config_path` accordingly).

2. Install the only external dependency:
   ```
   pip install requests
   ```

3. Open `AutoCollectScript.py` in any text editor and fill in the configuration section at the top of the file (see below).

---

## Configuration

All settings are at the **top of `AutoCollectScript.py`** in the `=== CONFIGURATION ===` section. Edit these values before your first run.

---

### `config_path`
**Default:** `"./config"`

Path to your ASF config folder. All `.json` files in this folder (except `ASF.json` and any `Manifest` files) are treated as bot accounts.

```python
config_path = "./config"
```

Change this if your config folder is in a different location:
```python
config_path = "C:/ArchiSteamFarm/config"
```

---

### `ASF_BASE_URL`
**Default:** `"http://127.0.0.1:1242"`

The base URL of your locally running ASF instance. Only change this if you have configured ASF to use a different port.

```python
ASF_BASE_URL = "http://127.0.0.1:1242"
```

---

### `exclude_bots`

A list of bot names to **exclude** from looting. Put your storage/main account names here so the script doesn't try to loot them. Matching is case-insensitive.

```python
exclude_bots = ["MyStorageAccount", "AnotherStorrageAccount"]
```
The Script should use the .json filename of the bot account.

---

### `storage_accounts`
**Default:** example entries

A dictionary used purely for **labeling the output summary**. Map a display name to the Steam64 ID of your storage account. This does not affect which accounts receive items — that is controlled by each bot's ASF config.

```python
storage_accounts = {
    "My Main Account": "76561198XXXXXXXXX"
}
```

To find your Steam64 ID, go to [steamid.io](https://steamid.io) and look up your profile.

If multiple display names share the same Steam64 ID, only one summary block will be printed (deduplication is automatic).

---

### `min_delay` / `max_delay`
**Default:** `7` / `25` (seconds)

Random wait time inserted **between each loot command**. Randomizing this helps avoid triggering Steam's trade throttling. Increase these if you have a very large number of bots or are experiencing trade failures.

```python
min_delay = 7
max_delay = 25
```

---

### `inventory_delay_min` / `inventory_delay_max`
**Default:** `7` / `20` (seconds)

Random wait time inserted **between each ASF inventory API request**. ASF forwards these to Steam, which rate-limits inventory fetches at the IP level. Keeping this above 5 seconds is recommended for large bot pools.

```python
inventory_delay_min = 7
inventory_delay_max = 20
```

---

### `COMMAND_TIMEOUT`
**Default:** `180` (seconds)

HTTP read timeout for `loot^` commands sent to ASF. The `loot^` command is **synchronous** — ASF holds the response open until the Steam trade offer has been created and mobile-confirmed. Under load (many bots, Steam per-IP throttling, bot session refreshes, 2FA polling) a single trade can take 60–120 seconds. Setting this too low causes false failures where the trade actually succeeded.

```python
COMMAND_TIMEOUT = 180
```

---

### `INVENTORY_TIMEOUT`
**Default:** `60` (seconds)

HTTP read timeout for ASF inventory API calls. Large inventories with multiple pages can be slow to fetch.

```python
INVENTORY_TIMEOUT = 60
```

---

### `APP_ID` / `CONTEXT_ID`
**Default:** `730` / `2`

The Steam App ID and inventory context ID to operate on. `730` is CS:GO / Counter-Strike 2, and context `2` is tradable items. **Do not change these** unless you are adapting the script for a different game.

```python
APP_ID = 730
CONTEXT_ID = 2
```

---

### `FILTER_KEYWORDS`
**Default:** `[]` (empty — all items included)

An optional list of keywords. When set, only items whose Steam `market_hash_name` contains at least one keyword (case-insensitive) will be counted in the summary. The loot command still sends everything regardless — this only affects the output display.

```python
# Show all items (default)
FILTER_KEYWORDS = []

# Show only cases in the summary
FILTER_KEYWORDS = ["Case", "Capsule"]
```

---

## Running the Script

1. Make sure ASF is running and all bots are logged in.
2. Open a terminal in the folder containing `AutoCollectScript.py`.
3. Type:
 
   python AutoCollectScript.py

That's it. The script will:
1. Discover all eligible bots from the config folder
2. Scan each bot's CS2 inventory via ASF IPC (pre-loot snapshot)
3. Send `loot^` commands to all bots one by one (with random delays)
4. Re-scan inventories to confirm delivery
5. Resolve any timed-out bots using the inventory delta
6. Print a full summary of everything transferred

**Typical runtime** depends on the number of bots and the configured delays. With 20 bots and default delays, expect roughly 5–10 minutes.

---

## Understanding the Output

The script prints progress as it runs, using the following indicators:

| Symbol | Meaning |
|--------|---------|
| 🔍 | Scanning a bot's inventory |
| 🤖 | Starting the inventory scan phase |
| 🚀 | Sending a loot command to a bot |
| ✅ | Loot command confirmed succeeded |
| ⏱️ | Loot command HTTP read timed out — trade still being verified via post-scan |
| ❌ | Loot command hard-failed (connection error, ASF error response) |
| ⚠️ | Warning (e.g. rate limit, inventory unavailable) |
| 💀 | Bot inventory was empty |
| ⏳ | Waiting between requests |
| 🧾 | Final summary section |
| 📋 | Per-account summary block |

**Example final output:**
```
=== 🧾 the full rundown, no cap ===

📋 My Main Account:
  My Main Account got: 42x Clutch Case
  My Main Account got: 17x Danger Zone Case
  My Main Account got: 5x CS:GO Weapon Case

✅ we done here, gg wp!
```

The summary shows only what was collected **in this run** from the bots. It does not show the total contents of your storage account.

---

## What to Do When Bots Fail

The script distinguishes two failure categories:

**Hard failure (❌)** — ASF returned an error response or the connection to ASF dropped entirely. The trade did not go through. Re-run the script to retry these bots.

**Timeout-pending (⏱️)** — The HTTP read for `loot^` exceeded `COMMAND_TIMEOUT` (default 180 s). This does **not** mean the trade failed — ASF was almost certainly still processing it. The script verifies these bots automatically using the post-loot inventory scan:
- If the bot's inventory emptied → the trade succeeded (false alarm on the timeout).
- If items are still on the bot → the trade did not complete; the bot is added to the redo list.

In both cases there is **no automatic retry**. Simply re-run the script — bot discovery and inventory scanning will pick up any bots that still have items.

Common reasons a bot might fail:
- The bot is not logged in to Steam
- The bot has a trade hold active (Steam Guard < 7 days)
- Steam returned a temporary error or was very slow (common under high load)
- ASF is not running or IPC is not reachable

To re-run only specific bots without waiting for all the others, you can temporarily remove the other bots' `.json` files from the config folder, run the script, then restore them — though typically a full re-run is simpler.

---

## Scheduling Automatic Runs

### Windows — Task Scheduler
1. Open **Task Scheduler** → Create Basic Task
2. Set the trigger (e.g., Daily at a specific time)
3. Set the action to: **Start a Program**
   - Program: `python`
   - Arguments: `AutoCollectScript.py`
   - Start in: the full path to the folder containing the script
4. Make sure ASF is already running before the scheduled task fires (add ASF as a separate startup task if needed)

### Linux / macOS — cron
Add a cron entry with `crontab -e`:
```
# Run every day at 3:00 AM
0 3 * * * cd /path/to/autocollect && python AutoCollectScript.py >> /path/to/autocollect/run.log 2>&1
```

---

## Troubleshooting

**❌ errors on every bot / "I fucking can't reach ASF"**
→ ASF is not running or IPC is not enabled. Start ASF first and verify `"IPC": true` is in `ASF.json`.

**⏱️ many bots showing as timeout-pending**
→ Steam is responding slowly under load. The post-loot scan will resolve most of these automatically. If bots still land in the redo list, increase `COMMAND_TIMEOUT` (e.g. `240`) or raise `min_delay`/`max_delay` to spread out the trade offers.

**Loot commands succeed but nothing arrives in the storage account**
→ The bot's `SteamUserPermissions` in its `.json` config does not grant `Master` (permission level 3) to the storage account. Double-check each bot config.

**Items are missing from the summary**
→ If `FILTER_KEYWORDS` is set, items not matching any keyword are excluded from the display. Set it to `[]` to see everything.

**Steam inventory requests are failing**
→ Steam's public inventory API has intermittent rate limits. Try increasing `inventory_delay_min` and `inventory_delay_max` (e.g., to `8` / `12`).

**The script crashes on startup with "No such file or directory: './config'"**
→ The `config_path` setting is wrong. Update it to the actual path of your ASF config folder.
