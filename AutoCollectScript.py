import os
import sys
import time
import random
import requests
from collections import Counter

# ==============================================================================
# CONFIGURATION — edit these values before running
# ==============================================================================

# Path to your ASF config folder (contains all bot .json files)
# Resolved relative to this script's location — so config/ must sit next to AutoCollectScript.py
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# ArchiSteamFarm IPC base URL (must be running before you start this script)
ASF_BASE_URL = "http://127.0.0.1:1242"
ASF_IPC_URL  = f"{ASF_BASE_URL}/Api/Command"

# Steam App ID and inventory context to operate on
# 730 = CS:GO / Counter-Strike 2, context 2 = tradable items
APP_ID     = 730
CONTEXT_ID = 2

# Bot accounts to EXCLUDE from looting (your storage/main accounts), same Name as the .json file
# Matching is case-insensitive
exclude_bots = [
    "YOUR_STORAGE_BOT_NAME_HERE",
    "ANOTHER_BOT_TO_EXCLUDE_IF_NEEDED"
    
]

# Storage/main accounts — used only to label the output summary
# Format: { "Display Name": "Steam64ID" }
storage_accounts = {
    "YOUR_STORAGE_BOT_NAME_HERE": "123456789012345678",
}

# Random delay range (seconds) between loot commands
min_delay = 7
max_delay = 25

# Random delay range (seconds) between ASF inventory API requests
# ASF forwards these to Steam's inventory API from your IP — Steam rate-limits at the
# IP level, so treat this similarly to the loot delay to avoid 429s during the scan/loot phase.
inventory_delay_min = 7
inventory_delay_max = 20

# HTTP read timeout (seconds) for ASF IPC calls.

COMMAND_TIMEOUT = 180

# HTTP read timeout (seconds) for ASF inventory calls. ASF forwards these to Steam,
# whose inventory endpoint can also be slow when paginating large bot inventories.
INVENTORY_TIMEOUT = 60

# Optional keyword filter for the summary output
# Leave empty [] to show all items
# Example: ["Case", "Capsule"] shows only cases and capsules
FILTER_KEYWORDS = []

# ==============================================================================
# HELPERS
# ==============================================================================

def typewrite(text: str, delay: float = 0.03, end: str = "\n") -> None:
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(end)
    sys.stdout.flush()


def random_delay():
    delay = random.randint(min_delay, max_delay)
    typewrite(f"⏳  holdup, layin low for {delay} secs so Steam don't beef with us...")
    time.sleep(delay)


def inventory_delay():
    time.sleep(random.randint(inventory_delay_min, inventory_delay_max))

# ==============================================================================
# BOT DISCOVERY
# Scans config_path for .json files, excludes ASF.json, Manifest files,
# and any bot names listed in exclude_bots (case-insensitive).
# ==============================================================================

if not os.path.isdir(config_path):
    typewrite(f"❌  yo what the fuck, config folder ain't even there: {config_path}")
    typewrite("    put the config/ folder in the same directory as this script, deadass")
    raise SystemExit(1)

bots = []

for filename in os.listdir(config_path):
    if not filename.endswith(".json"):
        continue
    lower = filename.lower()
    if lower == "asf.json":
        continue
    if "manifest" in lower:
        continue
    bot_name = filename[:-5]  # strip .json
    if bot_name.lower() in [b.lower() for b in exclude_bots]:
        continue
    bots.append(bot_name)

bots.sort(key=str.casefold)

if not bots:
    typewrite("⚠️  bruh there ain't a single bot in the config folder, we out — fix ya config_path")
    raise SystemExit(0)

typewrite(f"🤖  aight bet, we got {len(bots)} bots locked and loaded, let's get this bread")

# ==============================================================================
# ASF API CLIENT
# ==============================================================================

# Reuse a single HTTP session so the TCP connection to ASF (loopback) is kept alive
# between calls. Avoids handshake overhead on every command/inventory request.
_session = requests.Session()


def send_command(command: str) -> str:
    """Send a single command to the ASF IPC endpoint.

    Returns one of:
      "ok"      — ASF confirmed the command succeeded
      "failed"  — ASF returned an explicit error / non-200 / connection error
      "timeout" — the local HTTP read timed out. With `loot^` this does NOT mean the
                  trade failed — ASF is almost certainly still processing it. The
                  post-loot inventory scan is the source of truth in that case.
    """
    try:
        response = _session.post(
            ASF_IPC_URL,
            json={"Command": command},
            timeout=(10, COMMAND_TIMEOUT),  # (connect, read) — connect is cheap on loopback
        )
        if response.status_code == 401:
            typewrite("❌  ASF said 401 — the fuck? you got IPCPassword set in ASF.json?")
            typewrite("    either kill that IPC password in ASF.json or we can't do shit")
            return "failed"
        if response.status_code != 200:
            typewrite(f"❌  what the hell, HTTP {response.status_code} came back on: {command}")
            return "failed"
        result = response.json().get("Result", "") or ""
        # Strip leading bot-name tag (ASF wraps output as "<BotName> message" or "BotName<br>message")
        if result.startswith("<") and ">" in result:
            inner = result.split(">", 1)[1].strip()
        elif "<br>" in result:
            inner = result.split("<br>", 1)[1].strip()
        else:
            inner = result.strip()
        typewrite(f"    ASF: {inner}")
        if any(word in inner.lower() for word in ["error", "failed", "denied", "unable"]):
            return "failed"
        return "ok"
    except requests.exceptions.ReadTimeout:
        typewrite(
            f"⏱️   ASF didn't respond in {COMMAND_TIMEOUT}s on: {command}"
        )
        typewrite(
            "    NOT markin this bot failed yet — Steam is just slow, ASF is probably still"
        )
        typewrite(
            "    finishin the trade. Post-loot inventory scan will tell us the truth."
        )
        return "timeout"
    except requests.exceptions.ConnectTimeout:
        typewrite(f"❌  ASF didn't even accept the TCP connect on: {command} — is it alive?")
        return "failed"
    except requests.exceptions.ConnectionError:
        typewrite(f"❌  I fucking can't reach ASF, is that shit even running? command was: {command}")
        return "failed"
    except Exception as e:
        typewrite(f"❌  yo something broke the fuck out on: {command} — {e}")
        return "failed"


# ==============================================================================
# ASF INVENTORY CLIENT
# Fetches inventory through ASF's own IPC API.
# ==============================================================================

def _get_field(obj: dict, *keys, default=""):
    """Return first non-None value from dict trying multiple key name variants."""
    for key in keys:
        val = obj.get(key)
        if val is not None:
            return val
    return default


def fetch_inventory_via_asf(bot_name: str) -> list[str] | None:
    """
    Fetch bot inventory directly through ASF IPC.
    Returns a flat list of market_hash_name strings, empty list if bot has no items,
    or None if this ASF version doesn't support the endpoint.
    """
    url = f"{ASF_BASE_URL}/Api/Bot/{bot_name}/Inventory/{APP_ID}/{CONTEXT_ID}"
    params = {"language": "english"}

    try:
        response = _session.get(url, params=params, timeout=(10, INVENTORY_TIMEOUT))

        if response.status_code == 401:
            typewrite("❌  ASF said 401 — the fuck? you got IPCPassword set in ASF.json?")
            typewrite("    either kill that IPC password in ASF.json or we can't do shit")
            return []
        if response.status_code == 404:
            return None  # Old ASF version without the inventory endpoint
        if response.status_code != 200:
            typewrite(f"⚠️   ASF inventory API said {response.status_code} for {bot_name}, skippin that fool")
            return []

        data = response.json()
        if not data.get("Success"):
            return []

        bot_data = (data.get("Result") or {}).get(bot_name, {})
        if not bot_data:
            return []

        # ASF returns Assets + Descriptions (Steam protobuf types).
        # Field names may be PascalCase or camelCase depending on ASF/SteamKit version.
        assets = bot_data.get("Assets") or bot_data.get("assets") or []
        descriptions = bot_data.get("Descriptions") or bot_data.get("descriptions") or []

        # Build (classid, instanceid) → market_hash_name lookup
        desc_map: dict[tuple[str, str], str] = {}
        for d in descriptions:
            classid = str(_get_field(d, "classid", "Classid", "ClassId", "ClassID") or "")
            instanceid = str(_get_field(d, "instanceid", "Instanceid", "InstanceId", "InstanceID") or "0")
            name = _get_field(d, "market_hash_name", "MarketHashName", "marketHashName", "name", "Name", default="Unknown")
            desc_map[(classid, instanceid)] = str(name)

        items = []
        for asset in assets:
            classid = str(_get_field(asset, "classid", "Classid", "ClassId", "ClassID") or "")
            instanceid = str(_get_field(asset, "instanceid", "Instanceid", "InstanceId", "InstanceID") or "0")
            amount = int(_get_field(asset, "amount", "Amount") or 1)
            name = desc_map.get((classid, instanceid), "Unknown")
            if not FILTER_KEYWORDS or any(k.lower() in name.lower() for k in FILTER_KEYWORDS):
                items.extend([name] * amount)

        return items

    except requests.exceptions.Timeout:
        typewrite(f"⚠️   ASF timed out fetching inventory for {bot_name} — Steam is bein slow, skippin")
        return []
    except requests.exceptions.ConnectionError:
        typewrite("❌  I fucking can't reach ASF, is that shit even running?")
        return []
    except Exception as e:
        typewrite(f"⚠️   something broke fetching inventory for {bot_name} via ASF: {e}")
        return []

# ==============================================================================
# COLLECTION ORCHESTRATOR
# ==============================================================================

# --- Step 1: Scan bot inventories (pre-loot snapshot) ---
typewrite("\n=== 🔍  aight let's peep what these bots are sittin on before we run it... ===")

per_bot_items: dict = {}  # { bot_name: Counter }
asf_inventory_unavailable = False

for i, bot in enumerate(bots, 1):
    if asf_inventory_unavailable:
        break

    typewrite(f"🔍  [{i}/{len(bots)}] sniffin around {bot}'s stash...")
    items = fetch_inventory_via_asf(bot)

    if items is None:
        asf_inventory_unavailable = True
        typewrite("⚠️   inventory check didn't work — upgrade ASF and run again for item counts")
        typewrite("    still gonna loot tho, don't trip")
        break

    if not items:
        typewrite(f"💀  [{i}/{len(bots)}] {bot} is broke as hell")
    else:
        typewrite(f"    {bot} holdin {len(items)} items")
    per_bot_items[bot] = Counter(items)

    if i < len(bots):
        inventory_delay()

# --- Step 2: Send loot commands ---
typewrite("\n=== 🚀  ight it's time to get this money, robbin every single one of dem bots ===")

failed_bots = []   # ASF/HTTP-level hard failures
pending_bots = []  # HTTP read timed out — trade may still be in flight, verify via post-scan

for i, bot in enumerate(bots, 1):
    command = f"loot^ {bot} {APP_ID} {CONTEXT_ID}"
    typewrite(f"\n🚀  [{i}/{len(bots)}] ayo {bot}, gimme all that loot, my dewd")

    status = send_command(command)

    if status == "ok":
        typewrite(f"✅  {bot} paid up, we eatin fr fr")
    elif status == "timeout":
        typewrite(f"⏳  {bot} is takin forever — gonna verify after the rescan")
        pending_bots.append(bot)
    else:
        typewrite(f"❌  {bot} fumbled the bag, puttin that shit on the list")
        failed_bots.append(bot)

    if i < len(bots):
        random_delay()

# --- Step 3: Compute expected items ---
expected_items: Counter = Counter()
for c in per_bot_items.values():
    expected_items += c

# --- Step 4: Post-loot bot scan ---
per_bot_after: dict = {}
if not asf_inventory_unavailable:
    typewrite(f"\n📸  rescannin em bots to see who actually paid up...")
    for i, bot in enumerate(bots, 1):
        typewrite(f"🔍  [{i}/{len(bots)}] post-loot check on {bot}...")
        items_after = fetch_inventory_via_asf(bot)
        if items_after is None:
            asf_inventory_unavailable = True
            typewrite("⚠️   inventory check failed on post-loot scan")
            break
        per_bot_after[bot] = Counter(items_after)
        if i < len(bots):
            inventory_delay()

# --- Step 5: Resolve "timeout" bots using the post-loot scan ---
# An HTTP read timeout on `loot^` does NOT mean the trade failed. Use the actual
# post-loot inventory delta as the source of truth.
unresolved_pending = []
if pending_bots and not asf_inventory_unavailable:
    typewrite(f"\n🕵️   checkin in on the {len(pending_bots)} bot(s) that timed out...")
    for bot in pending_bots:
        before = per_bot_items.get(bot, Counter())
        after = per_bot_after.get(bot, Counter())
        # Did anything actually leave this bot?
        delta = before - after
        if sum(delta.values()) > 0 and sum(after.values()) == 0:
            typewrite(f"    ✅  {bot} actually delivered — false alarm on the timeout")
        elif sum(delta.values()) > 0:
            typewrite(f"    🟡  {bot} partially delivered ({sum(delta.values())} sent, {sum(after.values())} stuck)")
            unresolved_pending.append(bot)
        else:
            typewrite(f"    ❌  {bot} timed out AND nothin moved — addin to the redo list")
            unresolved_pending.append(bot)
elif pending_bots:
    # Inventory verification not available — we have to assume timeouts need a retry.
    unresolved_pending = list(pending_bots)

# --- Print expected items ---
if expected_items:
    typewrite(f"\n📋  We should be gettin — {sum(expected_items.values())} items:")
    for item_name, qty in sorted(expected_items.items(), key=lambda x: x[1], reverse=True):
        typewrite(f"    {qty}x {item_name}")
        time.sleep(0.2)
elif not asf_inventory_unavailable:
    typewrite("\n  all bots were giga broke fam, nothin inbound")

# ==============================================================================
# SUMMARY PRINTER
# ==============================================================================

typewrite("\n=== 🧾  here's the whole rundown, on god ===")
time.sleep(1)

if not asf_inventory_unavailable:
    confirmed_sent: Counter = Counter()
    still_on_bots: Counter = Counter()
    for bot, before in per_bot_items.items():
        after = per_bot_after.get(bot, Counter())
        confirmed_sent += before - after
        still_on_bots += after

    if confirmed_sent:
        typewrite(f"\n✅  CONFIRMED SENT — {sum(confirmed_sent.values())} items left the bots:")
        for item_name, qty in sorted(confirmed_sent.items(), key=lambda x: x[1], reverse=True):
            typewrite(f"    {qty}x {item_name}")
            time.sleep(0.3)
    else:
        typewrite("\n⚠️   nothin showed up in the Storage yet — Trade acceptance be foolin around?")

    missing: Counter = Counter({k: v for k, v in (expected_items - confirmed_sent).items() if v > 0})
    if missing:
        typewrite(f"\n❌  STILL ON BOTS — {sum(missing.values())} items didn't move:")
        for item_name, qty in sorted(missing.items(), key=lambda x: x[1], reverse=True):
            source_bots = [b for b, c in per_bot_after.items() if c.get(item_name, 0) > 0]
            sources = ", ".join(source_bots) if source_bots else "unknown"
            typewrite(f"    {qty}x {item_name}  ← still at: {sources}")
            time.sleep(0.3)
        typewrite("    trades might still be in flight — check manually if needed")
    elif confirmed_sent:
        typewrite("\n🎉  EVERYTHING LEFT THE BOTS, all items on the way!")
else:
    typewrite("\n⚠️   couldn't verify delivery — ASF inventory endpoint unavailable")
    if expected_items:
        typewrite(f"    expected {sum(expected_items.values())} items to transfer (see list above)")

if failed_bots:
    typewrite(f"\n⚠️   these bitch-ass bots didn't come through, run the script again to catch they ass:")
    time.sleep(3)
    for bot in failed_bots:
        typewrite(f"    • {bot}")
        time.sleep(0.5)

if unresolved_pending:
    typewrite(
        f"\n⏱️   these bots timed out and the trade didn't fully land — re-run the script to retry:"
    )
    time.sleep(2)
    for bot in unresolved_pending:
        typewrite(f"    • {bot}")
        time.sleep(0.3)

typewrite("\n✅  we done, got the bags, cya nerd!")
