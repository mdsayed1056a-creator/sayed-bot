#!/usr/bin/env python3
TELEGRAM_TOKEN = "9155762876:AAHOecyJVlnADSpp_wOHUxvYXhBs_NzWwhk"
TELEGRAM_OWNER = 6927583661
VALID_KEY      = "SAYED_FB"

import os, re, time, random, requests, threading, asyncio
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

requests.urllib3.disable_warnings()

HOME        = os.path.expanduser("~")
DATA_DIR    = os.path.join(HOME, ".sayed_users")
AUTHED_FILE = os.path.join(HOME, ".sayed_authed")
os.makedirs(DATA_DIR, exist_ok=True)

lock        = threading.Lock()
authed_lock = threading.Lock()

# ─── per-user paths ───────────────────────────────────────────
def user_dir(uid):
    d = os.path.join(DATA_DIR, str(uid))
    os.makedirs(d, exist_ok=True)
    return d

def pw_file(uid):   return os.path.join(user_dir(uid), "pw.txt")
def ok_file(uid):   return os.path.join(user_dir(uid), "OK.txt")
def cp_file(uid):   return os.path.join(user_dir(uid), "CP.txt")
def fail_file(uid): return os.path.join(user_dir(uid), "FAIL.txt")

def load_pw(uid):
    try:
        with open(pw_file(uid)) as f: return f.read().strip()
    except: return ""

def store_pw(uid, pw):
    try:
        with open(pw_file(uid), "w") as f: f.write(pw)
    except: pass

def user_oks(uid):
    results = []
    try:
        with open(ok_file(uid)) as f:
            for line in f:
                line = line.strip()
                if line: results.append(line)
    except: pass
    return results

def save_ok_user(uid, fb_uid, contact, pw, ck_str):
    with lock:
        with open(ok_file(uid), "a") as f:
            f.write(f"UID:{fb_uid}|PHONE:{contact}|PASS:{pw}|COOKIE:{ck_str}\n")

def save_cp_user(uid, contact, pw):
    with lock:
        with open(cp_file(uid), "a") as f:
            f.write(f"CP|PHONE:{contact}|PASS:{pw}\n")

def save_fail_user(uid, contact, reason):
    with lock:
        with open(fail_file(uid), "a") as f:
            f.write(f"FAIL|PHONE:{contact}|REASON:{reason[:200]}\n")

# ─── stats per user ───────────────────────────────────────────
def user_stats(uid):
    def count(path):
        try:
            with open(path) as f: return sum(1 for l in f if l.strip())
        except: return 0
    return count(ok_file(uid)), count(cp_file(uid)), count(fail_file(uid))

# ─── auth ─────────────────────────────────────────────────────
def load_authed():
    try:
        with open(AUTHED_FILE) as f:
            return set(int(x) for x in f.read().split() if x)
    except: return set()

def save_authed(uid_set):
    try:
        with open(AUTHED_FILE, "w") as f:
            f.write("\n".join(str(x) for x in uid_set))
    except: pass

authed_users = load_authed()

def is_authed(uid):
    if TELEGRAM_OWNER != 0 and uid == TELEGRAM_OWNER: return True
    with authed_lock: return uid in authed_users

def add_auth(uid):
    with authed_lock:
        authed_users.add(uid)
        save_authed(authed_users)

# ─── user-agent ───────────────────────────────────────────────
try:
    _ua = UserAgent()
    def rand_ua():
        mob = (f"Mozilla/5.0 (Linux; Android 13; Pixel 7) "
               f"AppleWebKit/537.36 (KHTML, like Gecko) "
               f"Chrome/120.0.{random.randint(1000,7000)}.0 Mobile Safari/537.36")
        try: return random.choice([_ua.random, mob])
        except: return mob
except:
    def rand_ua():
        return ("Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.6099.144 Mobile Safari/537.36")

FIRSTS = ["Maria","Angel","Andrea","Ashley","Bianca","Camille","Carla","Diana",
          "Ella","Erika","Faith","Hannah","Jasmine","Jessica","Joanna","Joy",
          "Julia","Katrina","Kimberly","Lauren","Mika","Nicole","Patricia",
          "Rachel","Rose","Samantha","Sofia","Stephanie","Vanessa","Victoria"]
LASTS  = ["Santos","Reyes","Cruz","Garcia","Mendoza","Bautista","Flores",
          "Aquino","Castillo","Navarro","Torres","Gonzales","Rivera","Ramos",
          "Fernandez","Dela Cruz","Villanueva","Santiago","Mercado","Manalo"]

def get_name():
    return random.choice(FIRSTS), random.choice(LASTS)

def extract_tokens(html):
    """Extract all necessary tokens from Facebook registration page"""
    data = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        for inp in soup.find_all("input"):
            n = inp.get("name"); v = inp.get("value", "")
            if n: data[n] = v
    except Exception as e:
        print(f"[ERROR] BeautifulSoup parsing failed: {e}")
    
    # Extract tokens from JavaScript/HTML
    patterns = {
        "lsd": [
            r'"LSD",\[\],\{"token":"([^"]+)"',
            r'name="lsd"\s+value="([^"]+)"',
            r'"lsd":"([^"]+)"'
        ],
        "jazoest": [
            r'jazoest[="\s:]+([0-9]+)',
            r'name="jazoest"\s+value="([^"]+)"'
        ],
        "fb_dtsg": [
            r'"DTSGInitData",\[\],\{"token":"([^"]+)"',
            r'name="fb_dtsg"\s+value="([^"]+)"',
            r'"fb_dtsg":"([^"]+)"'
        ],
        "reg_instance": [
            r'"reg_instance"\s*[=:,\[]+\s*"([^"]{6,})"',
            r'name="reg_instance"\s+value="([^"]+)"'
        ],
        "reg_impression_id": [
            r'"reg_impression_id"\s*[=:,\[]+\s*"([^"]{6,})"',
            r'name="reg_impression_id"\s+value="([^"]+)"'
        ],
        "logger_id": [
            r'"logger_id"\s*[=:,\[]+\s*"([^"]{6,})"',
            r'name="logger_id"\s+value="([^"]+)"'
        ],
    }
    
    for key, pats in patterns.items():
        if not data.get(key):
            for pat in pats:
                m = re.search(pat, html)
                if m:
                    data[key] = m.group(1)
                    break
    
    return data

def make_session():
    ses = requests.Session()
    ua  = rand_ua()
    ses.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    })
    ses.cookies.set("locale", "en_US", domain=".facebook.com")
    return ses, ua

def load_reg_page(ses, ua):
    """Try multiple Facebook registration endpoints"""
    endpoints = [
        "https://m.facebook.com/r.php",
        "https://www.facebook.com/r.php",
        "https://m.facebook.com/reg/",
        "https://www.facebook.com/reg/"
    ]
    
    for url in endpoints:
        try:
            print(f"[INFO] Trying: {url}")
            r = ses.get(url, timeout=15, headers={"User-Agent": ua})
            print(f"[INFO] Status: {r.status_code}, Length: {len(r.text)}")
            
            tokens = extract_tokens(r.text)
            print(f"[INFO] Tokens found: {list(tokens.keys())}")
            
            # Check if we got a valid registration page
            if tokens.get("lsd") or tokens.get("jazoest") or "reg_email" in r.text or "birthday" in r.text.lower():
                print(f"[SUCCESS] Valid registration page found at: {url}")
                return r.text, tokens, url
        except Exception as e:
            print(f"[ERROR] Failed to load {url}: {e}")
            continue
    
    print("[ERROR] All endpoints failed")
    return "", {}, ""

def submit_reg(ses, ua, url, fn, ln, contact, pw, tokens):
    """Submit registration form"""
    dob_d = str(random.randint(10, 25))
    dob_m = str(random.randint(1, 12))
    dob_y = str(random.randint(1985, 2000))
    enc   = f"#PWD_BROWSER:0:{int(time.time())}:{pw}"
    
    # Build payload with all available tokens
    payload = {
        "firstname": fn,
        "lastname": ln,
        "reg_email__": contact,
        "reg_email_confirmation__": contact,
        "birthday_day": dob_d,
        "birthday_month": dob_m,
        "birthday_year": dob_y,
        "sex": str(random.choice([1, 2])),
        "reg_passwd__": pw,
        "encpass": enc,
        "terms": "on",
        "submit": "Sign Up",
    }
    
    # Add all extracted tokens
    for key, value in tokens.items():
        if value:
            payload[key] = value
    
    # Determine the submit URL
    if "r.php" in url:
        submit_url = url.replace("r.php", "r.php")
    elif "reg/" in url:
        submit_url = url + "submit/"
    else:
        submit_url = url
    
    hdrs = {
        "User-Agent": ua,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": url,
        "Origin": "https://m.facebook.com" if "m.facebook" in url else "https://www.facebook.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    print(f"[INFO] Submitting to: {submit_url}")
    print(f"[INFO] Payload keys: {list(payload.keys())}")
    
    r = ses.post(submit_url, data=payload, headers=hdrs, timeout=20, allow_redirects=True)
    print(f"[INFO] Response status: {r.status_code}, URL: {r.url}")
    
    return r, dob_d, dob_m, dob_y

MAX_RETRY = 3

def create_one(uid, contact, pw):
    """Create one Facebook account with retry logic"""
    last_error = ""
    
    for attempt in range(1, MAX_RETRY + 1):
        print(f"\n[ATTEMPT {attempt}/{MAX_RETRY}] Creating account for: {contact}")
        
        try:
            ses, ua = make_session()
            html, tokens, url = load_reg_page(ses, ua)
            
            if not html:
                last_error = "Failed to load registration page"
                print(f"[ERROR] {last_error}")
                time.sleep(3)
                continue
            
            if not tokens:
                last_error = "No tokens extracted from page"
                print(f"[ERROR] {last_error}")
                time.sleep(3)
                continue
            
            fn, ln = get_name()
            print(f"[INFO] Name: {fn} {ln}")
            
            r2, dob_d, dob_m, dob_y = submit_reg(ses, ua, url, fn, ln, contact, pw, tokens)
            
            ck = ses.cookies.get_dict()
            fb_uid = ck.get("c_user", "")
            ck_str = "; ".join(f"{k}={v}" for k, v in ck.items())
            dob = f"{dob_d}-{dob_m}-{dob_y}"
            
            print(f"[INFO] UID: {fb_uid}")
            print(f"[INFO] Cookies: {list(ck.keys())}")
            
            is_cp = ("checkpoint" in r2.url.lower() or 
                    "checkpoint" in r2.text[:1000].lower() or
                    "confirm" in r2.text[:1000].lower())
            
            if fb_uid and fb_uid != "0":
                print(f"[SUCCESS] Account created! UID: {fb_uid}")
                save_ok_user(uid, fb_uid, contact, pw, ck_str)
                return "ok", fb_uid, ck_str, dob
            elif is_cp:
                print(f"[CHECKPOINT] Account needs verification")
                save_cp_user(uid, contact, pw)
                return "checkpoint", "", "", ""
            else:
                # Check for specific error messages
                error_text = r2.text[:500].lower()
                if "already" in error_text or "exists" in error_text:
                    last_error = "Phone number already registered"
                elif "invalid" in error_text:
                    last_error = "Invalid phone number"
                elif "blocked" in error_text or "rate" in error_text:
                    last_error = "Rate limited or blocked"
                else:
                    last_error = f"Unknown error (status: {r2.status_code})"
                
                print(f"[ERROR] {last_error}")
                
                if attempt < MAX_RETRY:
                    wait_time = random.uniform(3, 6)
                    print(f"[INFO] Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                    continue
                    
        except Exception as e:
            last_error = f"Exception: {str(e)[:100]}"
            print(f"[EXCEPTION] {last_error}")
            if attempt < MAX_RETRY:
                time.sleep(3)
                continue
    
    save_fail_user(uid, contact, last_error)
    return "error", "", "", last_error

# ═══════════════════════════════════════════════════════════════
# KEYBOARDS & UI DESIGN
# ═══════════════════════════════════════════════════════════════

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create Account", callback_data="menu_create")],
        [InlineKeyboardButton("📊 Statistics", callback_data="menu_stats"),
         InlineKeyboardButton("📜 Recent Accounts", callback_data="menu_ok")],
        [InlineKeyboardButton("⚙️ Set Password", callback_data="menu_setpw"),
         InlineKeyboardButton("❓ Help & Support", callback_data="menu_help")]
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Home", callback_data="menu_home")]
    ])

async def show_home(target, uid, edit=False):
    saved = load_pw(uid)
    pw_status = f"✅ `{saved}`" if saved else "❌ _Not Set_"
    
    msg = (
        "⚡ *SAYED TOOLS - PREMIUM* ⚡\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "🤖 *Advanced FB Account Creator*\n\n"
        f"🔑 *Current Password:* {pw_status}\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "👇 *Select an option below:*"
    )
    
    if edit:
        await target.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
    else:
        await target.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

# ═══════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_authed(uid):
        await show_home(update.message, uid)
        return
    
    ctx.user_data["state"] = "wait_key"
    msg = (
        "🔐 *ACCESS RESTRICTED*\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "Welcome to *SAYED TOOLS*!\n\n"
        "Please enter your **Active Key** 🔑 below to continue.\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if not is_authed(uid):
        await query.answer("❌ Please provide a valid key first via /start", show_alert=True)
        return
    
    data = query.data

    if data == "menu_home":
        await show_home(query, uid, edit=True)

    elif data == "menu_stats":
        ok, cp, fl = user_stats(uid)
        total = ok + cp + fl
        msg = (
            "📊 *ACCOUNT STATISTICS*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"✅ *Alive:* `{ok}`\n"
            f"⚠️ *Checkpoint:* `{cp}`\n"
            f"❌ *Failed:* `{fl}`\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"📦 *Total Processed:* `{total}`"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_ok":
        lines_raw = user_oks(uid)
        if not lines_raw:
            msg = (
                "📭 *NO ACCOUNTS YET*\n"
                "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
                "You haven't created any accounts yet.\n"
                "Use ➕ *Create Account* to start!"
            )
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())
            return
        
        recent = lines_raw[-3:]
        lines = []
        for l in reversed(recent):
            parts = dict(p.split(":", 1) for p in l.split("|") if ":" in p)
            lines.append(
                "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
                f"🆔 *UID:* `{parts.get('UID','?')}`\n"
                f"📱 *Phone:* `{parts.get('PHONE','?')}`\n"
                f"🔑 *Pass:* `{parts.get('PASS','?')}`"
            )
        
        msg = "✅ *RECENT ACCOUNTS*\n" + "\n".join(lines)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_setpw":
        ctx.user_data["state"] = "setpw"
        msg = (
            "⚙️ *SET PASSWORD*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "Please type your desired password below.\n"
            "💡 *Tip:* Use a strong, memorable password."
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_create":
        ctx.user_data["state"] = "wait_phone"
        saved = load_pw(uid)
        pw_hint = f"\n\n💡 *Saved Pass:* `{saved}` (will be used automatically)" if saved else ""
        msg = (
            "➕ *CREATE NEW ACCOUNT*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "Please provide the phone number.\n"
            "📌 *Format:* Any valid phone with country code\n"
            "Example: `+8801XXXXXXXXX` or `+2376XXXXXXXX`"
            f"{pw_hint}"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_help":
        msg = (
            "❓ *HOW TO USE*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "1️⃣ *Set Password* → Save your default password.\n"
            "2️⃣ *Create Account* → Provide a valid phone number.\n"
            "3️⃣ *Copy Data* → Save the generated UID & Cookie.\n\n"
            "💡 *Note:* Each user's data is stored separately and securely.\n"
            "⚠️ *Warning:* Use fresh phone numbers only!"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

# ═══════════════════════════════════════════════════════════════
# TEXT HANDLER
# ═══════════════════════════════════════════════════════════════

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    state = ctx.user_data.get("state", "")

    if not is_authed(uid):
        if text == VALID_KEY:
            add_auth(uid)
            ctx.user_data["state"] = ""
            await update.message.reply_text("✅ *ACCESS GRANTED!* Tools Active.", parse_mode="Markdown")
            await show_home(update.message, uid)
        else:
            await update.message.reply_text("❌ *INVALID KEY!* Please try again with the correct active key.", parse_mode="Markdown")
        return

    if state == "setpw":
        store_pw(uid, text)
        ctx.user_data["state"] = ""
        msg = (
            "✅ *PASSWORD SAVED!*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"Your new password is set to: `{text}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

    elif state == "wait_phone":
        phone = text if text.startswith('+') else '+' + text
        ctx.user_data["phone"] = phone
        saved = load_pw(uid)
        if saved:
            ctx.user_data["state"] = ""
            await _do_create(update, uid, phone, saved)
        else:
            ctx.user_data["state"] = "wait_pw"
            msg = (
                f"📱 *Phone:* `{phone}`\n"
                "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
                "Now, please provide the *Password* 👇"
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif state == "wait_pw":
        phone = ctx.user_data.get("phone", "")
        ctx.user_data["state"] = ""
        if not phone:
            await update.message.reply_text("❌ *ERROR:* Phone number not found. Please start over.", reply_markup=main_keyboard())
            return
        await _do_create(update, uid, phone, text)

    else:
        await show_home(update.message, uid)

async def _do_create(update, uid, phone, pw):
    msg = await update.message.reply_text(
        "🚀 *PROCESSING REQUEST...*\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"📱 *Phone:* `{phone}`\n"
        f"🔑 *Pass:* `{pw}`\n\n"
        "⏳ *Please wait while we create your account...*")
    
    loop = asyncio.get_event_loop()
    result, fb_uid, ck_str, error_msg = await loop.run_in_executor(None, create_one, uid, phone, pw)

    if result == "ok":
        p1 = ck_str[:300]
        p2 = ck_str[300:]
        
        success_msg = (
            "🎉 *ACCOUNT CREATED SUCCESSFULLY!*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"📱 *Phone:* `{phone}`\n"
            f"🆔 *UID:* `{fb_uid}`\n"
            f"🔑 *Pass:* `{pw}`\n\n"
            "🍪 *COOKIE (Part 1):*\n"
            f"`{p1}`"
        )
        await msg.edit_text(success_msg, parse_mode="Markdown")
        
        if p2:
            await update.message.reply_text(
                "🍪 *COOKIE (Part 2):*\n"
                f"`{p2}`", parse_mode="Markdown")
                
        await update.message.reply_text(
            "🏠 *What would you like to do next?*", reply_markup=main_keyboard())
            
    elif result == "checkpoint":
        await msg.edit_text(
            "⚠️ *CHECKPOINT DETECTED*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"📱 *Phone:* `{phone}`\n\n"
            "The account was created but requires verification.",
            parse_mode="Markdown")
        await update.message.reply_text("🏠 *Return to Main Menu*", reply_markup=main_keyboard())
        
    else:
        await msg.edit_text(
            "❌ *CREATION FAILED*\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"📱 *Phone:* `{phone}`\n"
            f"⚠️ *Error:* {error_msg}\n\n"
            "💡 *Tips:*\n"
            "• Use a fresh phone number\n"
            "• Wait 5-10 minutes before retrying\n"
            "• Try a different country code",
            parse_mode="Markdown")
        await update.message.reply_text("🏠 *Return to Main Menu*", reply_markup=main_keyboard())

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("\033[1;92m[SAYED] Bot starting...\033[0m")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start", "🔥 SAYED TOOLS")])
            
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)
