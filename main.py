#!/usr/bin/env python3
TELEGRAM_TOKEN = "9155762876:AAHOecyJVlnADSpp_wOHUxvYXhBs_NzWwhk"
TELEGRAM_OWNER = 6927583661
VALID_KEY      = "SAYED_FB"

import os, re, time, random, requests, threading, asyncio
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

requests.urllib3.disable_warnings()

HOME        = os.path.expanduser("~")
DATA_DIR    = os.path.join(HOME, ".sayed_users")
AUTHED_FILE = os.path.join(HOME, ".sayed_authed")
os.makedirs(DATA_DIR, exist_ok=True)

lock        = threading.Lock()
authed_lock = threading.Lock()

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
    try:
        with open(ok_file(uid)) as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

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
            f.write(f"FAIL|PHONE:{contact}|REASON:{reason[:120]}\n")

def user_stats(uid):
    def count(path):
        try:
            with open(path) as f: return sum(1 for l in f if l.strip())
        except: return 0
    return count(ok_file(uid)), count(cp_file(uid)), count(fail_file(uid))

def load_authed():
    try:
        with open(AUTHED_FILE) as f:
            return set(int(x) for x in f.read().split() if x)
    except: return set()

def save_authed(s):
    try:
        with open(AUTHED_FILE, "w") as f:
            f.write("\n".join(str(x) for x in s))
    except: pass

authed_users = load_authed()

def is_authed(uid):
    if TELEGRAM_OWNER != 0 and uid == TELEGRAM_OWNER: return True
    with authed_lock: return uid in authed_users

def add_auth(uid):
    with authed_lock:
        authed_users.add(uid)
        save_authed(authed_users)

# ─── UA pool ──────────────────────────────────────────────────
UA_LIST = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Samsung SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.193 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.111 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

def rand_ua(): return random.choice(UA_LIST)

FIRSTS = ["Maria","Angel","Andrea","Ashley","Bianca","Camille","Carla","Diana",
          "Ella","Erika","Faith","Hannah","Jasmine","Jessica","Joanna","Joy",
          "Julia","Katrina","Kimberly","Lauren","Mika","Nicole","Patricia",
          "Rachel","Rose","Samantha","Sofia","Stephanie","Vanessa","Victoria",
          "Abigail","Chloe","Elena","Grace","Iris","Jenny","Linda","Monica",
          "Nadia","Olivia","Paula","Rita","Sandra","Tina","Uma","Vera","Wendy"]

LASTS  = ["Santos","Reyes","Cruz","Garcia","Mendoza","Bautista","Flores",
          "Aquino","Castillo","Navarro","Torres","Gonzales","Rivera","Ramos",
          "Fernandez","Dela Cruz","Villanueva","Santiago","Mercado","Manalo",
          "Lopez","Perez","Rodriguez","Martinez","Hernandez","Diaz","Morales",
          "Jimenez","Romero","Alvarado","Guerrero","Medina","Chavez","Ruiz"]

def get_name():
    return random.choice(FIRSTS), random.choice(LASTS)

# ─── token extraction ─────────────────────────────────────────
def extract_tokens(html):
    data = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        for inp in soup.find_all("input"):
            n = inp.get("name",""); v = inp.get("value","")
            if n: data[n] = v
    except: pass

    patterns = {
        "lsd":               [r'"LSD",\[\],\{"token":"([^"]+)"',
                              r'name="lsd"\s+value="([^"]+)"',
                              r'"lsd":"([^"]+)"'],
        "jazoest":           [r'jazoest=([0-9]+)',
                              r'name="jazoest"\s+value="([0-9]+)"'],
        "fb_dtsg":           [r'"DTSGInitData",\[\],\{"token":"([^"]+)"',
                              r'"fb_dtsg":"([^"]+)"'],
        "reg_instance":      [r'"reg_instance"\s*[=:,\[]+\s*"([^"]{6,})"'],
        "reg_impression_id": [r'"reg_impression_id"\s*[=:,\[]+\s*"([^"]{6,})"'],
        "logger_id":         [r'"logger_id"\s*[=:,\[]+\s*"([^"]{6,})"'],
    }
    for key, pats in patterns.items():
        if not data.get(key):
            for pat in pats:
                m = re.search(pat, html)
                if m:
                    data[key] = m.group(1)
                    break
    return data

# ─── registration core ────────────────────────────────────────
SERVERS = [
    "limited.facebook.com",
    "m.facebook.com",
    "www.facebook.com",
]

def make_session(ua):
    ses = requests.Session()
    ses.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    })
    ses.cookies.set("locale", "en_US", domain=".facebook.com")
    ses.cookies.set("wd", "412x892",   domain=".facebook.com")
    return ses

def load_reg_page(ses, ua, server):
    try:
        url = f"https://{server}/reg/"
        r   = ses.get(url, timeout=20,
                      headers={"Host": server, "Referer": f"https://{server}/"},
                      allow_redirects=True)
        if r.status_code == 200 and ("reg_email" in r.text or "birthday" in r.text or "signup" in r.text.lower()):
            tokens = extract_tokens(r.text)
            return r.text, tokens
    except: pass
    return "", {}

def try_create(contact, pw):
    ua  = rand_ua()
    for server in SERVERS:
        ses    = make_session(ua)
        html, tokens = load_reg_page(ses, ua, server)
        if not html:
            continue

        fn, ln = get_name()
        dob_d  = str(random.randint(1, 28))
        dob_m  = str(random.randint(1, 12))
        dob_y  = str(random.randint(1990, 2000))
        ts     = int(time.time())
        enc    = f"#PWD_BROWSER:0:{ts}:{pw}"

        payload = {
            "firstname":              fn,
            "lastname":               ln,
            "reg_email__":            contact,
            "reg_email_confirmation__": contact,
            "reg_passwd__":           pw,
            "encpass":                enc,
            "birthday_day":           dob_d,
            "birthday_month":         dob_m,
            "birthday_year":          dob_y,
            "sex":                    "2",
            "ns":                     "1",
            "ccp":                    "2",
            "locale":                 "en_US",
            "submission_request":     "true",
            "submit":                 "Sign Up",
            "terms":                  "on",
        }

        # inject extracted tokens
        for k in ("lsd","jazoest","fb_dtsg","reg_instance",
                  "reg_impression_id","logger_id"):
            if tokens.get(k):
                payload[k] = tokens[k]

        hdrs = {
            "Host":            server,
            "User-Agent":      ua,
            "Content-Type":    "application/x-www-form-urlencoded",
            "Referer":         f"https://{server}/reg/",
            "Origin":          f"https://{server}",
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "upgrade-insecure-requests": "1",
        }

        try:
            r2 = ses.post(f"https://{server}/reg/submit/",
                          data=payload, headers=hdrs,
                          timeout=25, allow_redirects=True)
        except Exception as e:
            continue

        ck     = ses.cookies.get_dict()
        fb_uid = ck.get("c_user", "")
        ck_str = "; ".join(f"{k}={v}" for k, v in ck.items())
        dob    = f"{dob_d}-{dob_m}-{dob_y}"

        is_cp = ("checkpoint" in r2.url.lower() or
                 "checkpoint" in r2.text[:1000].lower())

        if fb_uid and fb_uid != "0":
            return "ok", fb_uid, ck_str, dob, fn, ln
        elif is_cp:
            return "checkpoint", "", ck_str, dob, fn, ln
        else:
            # debug: check why failed
            if "confirm" in r2.text.lower() or "verify" in r2.text.lower():
                return "checkpoint", "", ck_str, dob, fn, ln
            continue

    return "error", "", "", "", "", ""

MAX_RETRY = 3

def create_one(uid, contact, pw):
    for attempt in range(1, MAX_RETRY + 1):
        result, fb_uid, ck_str, dob, fn, ln = try_create(contact, pw)
        if result == "ok":
            save_ok_user(uid, fb_uid, contact, pw, ck_str)
            return "ok", fb_uid, ck_str, dob
        elif result == "checkpoint":
            save_cp_user(uid, contact, pw)
            return "checkpoint", "", "", ""
        else:
            if attempt < MAX_RETRY:
                time.sleep(random.uniform(2, 4))
                continue
    save_fail_user(uid, contact, "all_servers_failed")
    return "error", "", "", ""

# ═══════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create Account", callback_data="menu_create"),
         InlineKeyboardButton("📊 Stats",          callback_data="menu_stats")],
        [InlineKeyboardButton("✅ Last Accounts",  callback_data="menu_ok"),
         InlineKeyboardButton("🔑 Set Password",   callback_data="menu_setpw")],
        [InlineKeyboardButton("📋 Help",           callback_data="menu_help")],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Home", callback_data="menu_home")]
    ])

async def show_home(target, uid, edit=False):
    saved   = load_pw(uid)
    pw_line = f"🔑 Saved Pass: `{saved}`" if saved else "🔑 Saved Pass: _none_"
    msg = (
        "🔥 *SAYED TOOLS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 Facebook Account Creator\n"
        f"{pw_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "নিচের button চাপো 👇"
    )
    if edit:
        await target.edit_message_text(
            msg, parse_mode="Markdown", reply_markup=main_keyboard())
    else:
        await target.reply_text(
            msg, parse_mode="Markdown", reply_markup=main_keyboard())

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_authed(uid):
        await show_home(update.message, uid)
        return
    ctx.user_data["state"] = "wait_key"
    await update.message.reply_text(
        "🔐 *SAYED TOOLS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "আপনার active key🔑 দিন",
        parse_mode="Markdown")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    if not is_authed(uid):
        await query.answer("❌ Key দিন আগে। /start", show_alert=True)
        return
    data = query.data

    if data == "menu_home":
        await show_home(query, uid, edit=True)

    elif data == "menu_stats":
        ok, cp, fl = user_stats(uid)
        await query.edit_message_text(
            f"📊 *STATISTICS*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Alive      : `{ok}`\n"
            f"⚠️ Checkpoint : `{cp}`\n"
            f"❌ Failed     : `{fl}`\n"
            f"📦 Total      : `{ok+cp+fl}`",
            parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_ok":
        lines_raw = user_oks(uid)
        if not lines_raw:
            await query.edit_message_text(
                "📭 *No accounts yet.*",
                parse_mode="Markdown", reply_markup=back_keyboard())
            return
        recent = lines_raw[-3:]
        lines  = []
        for l in reversed(recent):
            parts = dict(p.split(":", 1) for p in l.split("|") if ":" in p)
            lines.append(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 `{parts.get('UID','?')}`\n"
                f"📱 `{parts.get('PHONE','?')}`\n"
                f"🔑 `{parts.get('PASS','?')}`"
            )
        await query.edit_message_text(
            "✅ *LAST ACCOUNTS*\n" + "\n".join(lines),
            parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_setpw":
        ctx.user_data["state"] = "setpw"
        await query.edit_message_text(
            "🔑 *Set Password*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "নতুন password type করে পাঠাও 👇",
            parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_create":
        ctx.user_data["state"] = "wait_phone"
        saved   = load_pw(uid)
        pw_hint = f"\n💡 Saved pass: `{saved}` (auto use হবে)" if saved else ""
        await query.edit_message_text(
            "➕ *Create Account*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 Phone number দাও (country code সহ)\n"
            "Example: `+8801XXXXXXXXX`" + pw_hint,
            parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "menu_help":
        await query.edit_message_text(
            "📋 *HOW TO USE*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ *Set Password* → password save করো\n"
            "2️⃣ *Create Account* → phone দাও\n"
            "3️⃣ UID + Cookie copy করো\n\n"
            "💡 প্রতিটা user এর data আলাদা",
            parse_mode="Markdown", reply_markup=back_keyboard())

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    text  = update.message.text.strip()
    state = ctx.user_data.get("state", "")

    if not is_authed(uid):
        if text == VALID_KEY:
            add_auth(uid)
            ctx.user_data["state"] = ""
            await update.message.reply_text("Tools Active ✅")
            await show_home(update.message, uid)
        else:
            await update.message.reply_text("আপনার active key🔑 ভূল❌")
        return

    if state == "setpw":
        store_pw(uid, text)
        ctx.user_data["state"] = ""
        await update.message.reply_text(
            f"✅ *Password saved!*\n`{text}`",
            parse_mode="Markdown", reply_markup=main_keyboard())

    elif state == "wait_phone":
        phone = text if text.startswith('+') else '+' + text
        ctx.user_data["phone"] = phone
        saved = load_pw(uid)
        if saved:
            ctx.user_data["state"] = ""
            await _do_create(update, uid, phone, saved)
        else:
            ctx.user_data["state"] = "wait_pw"
            await update.message.reply_text(
                f"📱 Phone: `{phone}`\n\n🔑 Password দাও 👇",
                parse_mode="Markdown", reply_markup=back_keyboard())

    elif state == "wait_pw":
        phone = ctx.user_data.get("phone", "")
        ctx.user_data["state"] = ""
        if not phone:
            await update.message.reply_text("❌ Phone নেই.",
                                             reply_markup=main_keyboard())
            return
        await _do_create(update, uid, phone, text)

    else:
        await show_home(update.message, uid)

async def _do_create(update, uid, phone, pw):
    msg = await update.message.reply_text(
        f"🚀 *Creating...*\n📱 `{phone}`\n🔑 `{pw}`\n\n⏳ Please wait...",
        parse_mode="Markdown")
    loop = asyncio.get_event_loop()
    result, fb_uid, ck_str, dob = await loop.run_in_executor(
        None, create_one, uid, phone, pw)

    if result == "ok":
        p1 = ck_str[:300]; p2 = ck_str[300:]
        await msg.edit_text(
            f"✅ *SUCCESS!*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 `{phone}`\n🆔 `{fb_uid}`\n"
            f"🔑 `{pw}`\n🎂 `{dob}`\n\n"
            f"🍪 *Cookie:*\n`{p1}`",
            parse_mode="Markdown")
        if p2:
            await update.message.reply_text(f"`{p2}`", parse_mode="Markdown")
        await update.message.reply_text("🏠 আরো বানাবে?",
                                         reply_markup=main_keyboard())
    elif result == "checkpoint":
        await msg.edit_text(
            f"⚠️ *CHECKPOINT*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 `{phone}`\n\n"
            "Account তৈরি হয়েছে কিন্তু verify চাইছে।",
            parse_mode="Markdown")
        await update.message.reply_text("🏠", reply_markup=main_keyboard())
    else:
        await msg.edit_text(
            f"❌ *FAILED*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 `{phone}`\n\n"
            "আবার চেষ্টা করো।",
            parse_mode="Markdown")
        await update.message.reply_text("🏠", reply_markup=main_keyboard())

if __name__ == '__main__':
    print("\033[1;92m[SAYED] Bot starting...\033[0m")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, text_handler))
    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start", "🔥 SAYED TOOLS")])
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)
