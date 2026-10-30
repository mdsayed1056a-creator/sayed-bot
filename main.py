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

def save_ok_user(uid, fb_uid, contact, pw, ck_str, confirmed):
    with lock:
        with open(ok_file(uid), "a") as f:
            status = "CONFIRMED" if confirmed else "NOT_CONFIRMED"
            f.write(f"UID:{fb_uid}|PHONE:{contact}|PASS:{pw}|STATUS:{status}|COOKIE:{ck_str}\n")

def save_cp_user(uid, contact, pw):
    with lock:
        with open(cp_file(uid), "a") as f:
            f.write(f"CP|PHONE:{contact}|PASS:{pw}\n")

def save_fail_user(uid, contact, reason):
    with lock:
        with open(fail_file(uid), "a") as f:
            f.write(f"FAIL|PHONE:{contact}|REASON:{reason[:80]}\n")

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
    data = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        for inp in soup.find_all("input"):
            n = inp.get("name"); v = inp.get("value", "")
            if n: data[n] = v
    except: pass
    for key, pat in {
        "lsd":               r'"LSD",\[\],\{"token":"([^"]+)"',
        "jazoest":           r'jazoest[="\s:]+([0-9]+)',
        "fb_dtsg":           r'"DTSGInitData",\[\],\{"token":"([^"]+)"',
        "reg_instance":      r'"reg_instance"\s*[=:,\[]+\s*"([^"]{6,})"',
        "reg_impression_id": r'"reg_impression_id"\s*[=:,\[]+\s*"([^"]{6,})"',
        "logger_id":         r'"logger_id"\s*[=:,\[]+\s*"([^"]{6,})"',
    }.items():
        if not data.get(key):
            m = re.search(pat, html)
            if m: data[key] = m.group(1)
    return data

def make_session(ua=None):
    if ua is None: ua = rand_ua()
    ses = requests.Session()
    ses.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    ses.cookies.set("locale", "en_US", domain=".facebook.com")
    return ses

MAX_RETRY  = 3
MOB_SERVER = "m.facebook.com"

# ─── phone exist check ────────────────────────────────────────
def check_phone_exists(contact, ua):
    ses = make_session(ua)
    try:
        r1 = ses.get(
            f"https://{MOB_SERVER}/login/identify/",
            headers={"Host": MOB_SERVER, "User-Agent": ua,
                     "Referer": f"https://{MOB_SERVER}/"},
            timeout=15)
        t1  = extract_tokens(r1.text)
        lsd = t1.get("lsd", "")
        r2  = ses.post(
            f"https://{MOB_SERVER}/login/identify/",
            data={"lsd": lsd, "email": contact,
                  "did_use_age_gate": "0",
                  "login_source": "find_friends",
                  "skip_api_login": "1", "submit": "Search"},
            headers={"Host": MOB_SERVER, "User-Agent": ua,
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Origin": f"https://{MOB_SERVER}",
                     "Referer": f"https://{MOB_SERVER}/login/identify/"},
            timeout=15)
        html = r2.text.lower()
        if any(s in html for s in ["couldn't find your account",
                                    "couldn't find", "no account found"]):
            return False
        if re.search(r'name="n"\s+value="([^"]+)"', r2.text): return True
        if any(s in html for s in ["recover your account",
                                    "reset your password",
                                    "confirm your identity"]): return True
        return False
    except: return False

# ═══════════════════════════════════════════════════════════════
# FORGOT FLOW CLASS — একটানা session
# ═══════════════════════════════════════════════════════════════

class ForgotFlow:
    def __init__(self, contact, ua):
        self.contact = contact
        self.ua      = ua
        self.ses     = make_session(ua)
        self.server  = MOB_SERVER
        self.lsd     = ""
        self.n       = ""
        self.ars     = ""
        self.sent    = False

    def _hdrs(self, referer=None):
        if referer is None:
            referer = f"https://{self.server}/"
        return {
            "Host": self.server,
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"https://{self.server}",
            "Referer": referer,
        }

    def identify(self):
        try:
            r1 = self.ses.get(
                f"https://{self.server}/login/identify/",
                headers=self._hdrs(), timeout=15)
            t1 = extract_tokens(r1.text)
            self.lsd = t1.get("lsd", "")

            r2 = self.ses.post(
                f"https://{self.server}/login/identify/",
                data={"lsd": self.lsd, "email": self.contact,
                      "did_use_age_gate": "0",
                      "login_source": "find_friends",
                      "skip_api_login": "1", "submit": "Search"},
                headers=self._hdrs(
                    f"https://{self.server}/login/identify/"),
                timeout=15)

            html2 = r2.text
            if "couldn't find" in html2.lower(): return False

            t2 = extract_tokens(html2)
            self.lsd = t2.get("lsd", self.lsd)
            n_m = re.search(r'name="n"\s+value="([^"]+)"', html2)
            self.n = n_m.group(1) if n_m else t2.get("n", "")
            ars_m = re.search(r'name="ars"\s+value="([^"]+)"', html2)
            self.ars = ars_m.group(1) if ars_m else t2.get("ars", "")
            return bool(self.n)
        except: return False

    def send_otp(self):
        code_sigs = [
            "enter the code", "confirmation code",
            "we sent", "6-digit", "check your",
            "sent you a code", "sms code", "type the code",
        ]
        for send_via in ("sms", "email"):
            try:
                r3 = self.ses.post(
                    f"https://{self.server}/recover/",
                    data={"lsd": self.lsd, "n": self.n,
                          "ars": self.ars,
                          "send_via": send_via,
                          "submit": "Continue"},
                    headers=self._hdrs(
                        f"https://{self.server}/login/identify/"),
                    timeout=15)
                html3 = r3.text
                t3 = extract_tokens(html3)
                if t3.get("lsd"): self.lsd = t3["lsd"]
                n3 = re.search(r'name="n"\s+value="([^"]+)"', html3)
                if n3: self.n = n3.group(1)
                ars3 = re.search(r'name="ars"\s+value="([^"]+)"', html3)
                if ars3: self.ars = ars3.group(1)
                if any(sig in html3.lower() for sig in code_sigs):
                    self.sent = True
                    return True
            except: continue
        return False

    def submit_code(self, code):
        try:
            r4 = self.ses.post(
                f"https://{self.server}/recover/",
                data={"lsd":    self.lsd,
                      "n":      self.n,
                      "ars":    self.ars,
                      "code":   code.strip(),
                      "submit": "Continue"},
                headers=self._hdrs(
                    f"https://{self.server}/recover/"),
                timeout=15, allow_redirects=True)

            html = r4.text.lower()
            url  = r4.url.lower()

            ok_str = [
                "choose a new password", "create new password",
                "reset your password", "new_password",
                "change password", "secure your account",
                "identity confirmed", "code was correct",
                "please choose", "enter new password",
                "password reset",
            ]
            ok_url = [
                "recover/password", "new_password",
                "recover/new", "checkpoint/block",
                "password/reset",
            ]
            bad_str = [
                "incorrect code", "wrong code", "invalid code",
                "doesn't match", "did not match",
                "code expired", "has expired",
            ]

            if any(s in html for s in ok_str):  return True
            if any(p in url  for p in ok_url):  return True
            if any(s in html for s in bad_str): return False
            if r4.status_code == 200 and "recover" not in url: return True
            return False
        except: return False


def prepare_forgot_flow(contact, ua):
    flow = ForgotFlow(contact, ua)
    ok   = flow.identify()
    if not ok: return flow, False
    sent = flow.send_otp()
    return flow, sent

def run_forgot_confirm(contact, code, ua):
    flow = ForgotFlow(contact, ua)
    if not flow.identify(): return False
    flow.send_otp()
    return flow.submit_code(code)

# ─── create account — multi server fallback ───────────────────
def create_one_ext(uid, contact, pw):
    servers = [
        "m.facebook.com",
        "limited.facebook.com",
        "mbasic.facebook.com",
    ]
    for attempt in range(1, MAX_RETRY + 1):
        ua  = rand_ua()
        ses = make_session(ua)

        for server in servers:
            try:
                reg_url = (f"https://{server}/r.php"
                           if server == "m.facebook.com"
                           else f"https://{server}/reg/")

                r0 = ses.get(reg_url, timeout=15,
                             headers={
                                 "User-Agent": ua,
                                 "Host": server,
                                 "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
                                 "Accept-Language": "en-US,en;q=0.9",
                                 "Referer": f"https://{server}/",
                             })
                tokens = extract_tokens(r0.text)
                if not (tokens.get("lsd") or
                        "reg_email" in r0.text or
                        "firstname" in r0.text):
                    continue

                dob_d = str(random.randint(10, 25))
                dob_m = str(random.randint(1, 12))
                dob_y = str(random.randint(1985, 2000))
                fn, ln = get_name()
                enc    = f"#PWD_BROWSER:0:{int(time.time())}:{pw}"

                payload = {
                    "lsd":               tokens.get("lsd", ""),
                    "jazoest":           tokens.get("jazoest", ""),
                    "fb_dtsg":           tokens.get("fb_dtsg", ""),
                    "reg_instance":      tokens.get("reg_instance", ""),
                    "reg_impression_id": tokens.get("reg_impression_id", ""),
                    "logger_id":         tokens.get("logger_id", ""),
                    "firstname":         fn,
                    "lastname":          ln,
                    "birthday_day":      dob_d,
                    "birthday_month":    dob_m,
                    "birthday_year":     dob_y,
                    "sex":               "2",
                    "encpass":           enc,
                    "reg_passwd__":      pw,
                    "reg_email__":       contact,
                    "reg_email_confirmation__": contact,
                    "ccp":               "2",
                    "ns":                "1",
                    "submission_request":"true",
                    "submit":            "Sign Up",
                    "terms":             "on",
                    "locale":            "en_US",
                }
                hdrs = {
                    "Host": server, "User-Agent": ua,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": reg_url,
                    "Origin": f"https://{server}",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                    "upgrade-insecure-requests": "1",
                }

                submit_url = f"https://{server}/reg/submit/"
                r2 = ses.post(submit_url, data=payload,
                              headers=hdrs, timeout=20,
                              allow_redirects=True)

                # m.facebook.com /reg/submit/ 404 → /r.php try
                if r2.status_code in (404, 400) and server == "m.facebook.com":
                    r2 = ses.post(
                        f"https://{server}/r.php",
                        data=payload,
                        headers={**hdrs, "Referer": reg_url},
                        timeout=20, allow_redirects=True)

                ck     = ses.cookies.get_dict()
                fb_uid = ck.get("c_user", "")
                ck_str = "; ".join(f"{k}={v}" for k, v in ck.items())
                dob    = f"{dob_d}-{dob_m}-{dob_y}"
                is_cp  = ("checkpoint" in r2.url.lower() or
                          "checkpoint" in r2.text[:600].lower())

                if fb_uid and fb_uid != "0":
                    return "ok", fb_uid, ck_str, dob, ua
                if is_cp:
                    save_cp_user(uid, contact, pw)
                    return "checkpoint", "", "", "", ua

            except: continue

        time.sleep(random.uniform(2, 4))

    save_fail_user(uid, contact, "all_servers_failed")
    return "error", "", "", "", rand_ua()

# ─── server test on startup ───────────────────────────────────
def test_reg_servers():
    ua = rand_ua()
    for server in ["m.facebook.com", "limited.facebook.com", "mbasic.facebook.com"]:
        try:
            url = (f"https://{server}/r.php"
                   if server == "m.facebook.com"
                   else f"https://{server}/reg/")
            r = requests.get(url, timeout=10,
                             headers={"User-Agent": ua, "Host": server})
            tokens   = extract_tokens(r.text)
            has_form = bool(tokens.get("lsd") or "reg_email" in r.text)
            print(f"[REG] {server}: {r.status_code} form={has_form}")
        except Exception as e:
            print(f"[REG] {server}: ❌ {str(e)[:50]}")

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

# ═══════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    if not is_authed(uid):
        await query.answer("❌ /start দিয়ে key দিন", show_alert=True)
        return
    data = query.data

    if data == "menu_home":
        ctx.user_data.pop("state", None)
        ctx.user_data.pop("pending_account", None)
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
            await query.edit_message_text("📭 *No accounts yet.*",
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
                f"🔑 `{parts.get('PASS','?')}`\n"
                f"📌 `{parts.get('STATUS','?')}`"
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
            "3️⃣ UID + Cookie দেখাবে\n"
            "4️⃣ Facebook OTP code দাও\n"
            "5️⃣ Confirm ✅ বা Not confirm ❌ দেখো\n\n"
            "🔑 Key একবার দিলে আর লাগবে না",
            parse_mode="Markdown", reply_markup=back_keyboard())

# ═══════════════════════════════════════════════════════════════
# TEXT HANDLER
# ═══════════════════════════════════════════════════════════════

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    text  = update.message.text.strip()
    state = ctx.user_data.get("state", "")

    if not is_authed(uid):
        if text == VALID_KEY:
            add_auth(uid)
            ctx.user_data["state"] = ""
            await update.message.reply_text(
                "✅ *Key Verified! Tools Active*",
                parse_mode="Markdown")
            await show_home(update.message, uid)
        else:
            await update.message.reply_text(
                "❌ *Key ভুল!*", parse_mode="Markdown")
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
            await _do_create(update, ctx, uid, phone, saved)
        else:
            ctx.user_data["state"] = "wait_pw"
            await update.message.reply_text(
                f"📱 Phone: `{phone}`\n\n🔑 Password দাও 👇",
                parse_mode="Markdown", reply_markup=back_keyboard())

    elif state == "wait_pw":
        phone = ctx.user_data.get("phone", "")
        ctx.user_data["state"] = ""
        if not phone:
            await update.message.reply_text(
                "❌ Phone নেই।", reply_markup=main_keyboard())
            return
        await _do_create(update, ctx, uid, phone, text)

    elif state == "wait_otp":
        pending = ctx.user_data.get("pending_account", {})
        if not pending:
            ctx.user_data["state"] = ""
            await update.message.reply_text(
                "❌ Session শেষ। নতুন account বানাও।",
                reply_markup=main_keyboard())
            return

        code    = text
        flow    = pending.get("flow")
        fb_uid  = pending["fb_uid"]
        phone   = pending["phone"]
        pw      = pending["pw"]
        ck_str  = pending["ck_str"]
        dob     = pending["dob"]
        bot_uid = pending["bot_uid"]
        ua      = pending["ua"]

        ctx.user_data["state"] = ""
        ctx.user_data.pop("pending_account", None)

        msg = await update.message.reply_text(
            "🔍 *Verifying code...*", parse_mode="Markdown")

        loop = asyncio.get_event_loop()

        def _verify():
            # Method 1: same session যেটায় OTP গেছে
            if flow and flow.n:
                if flow.submit_code(code):
                    return True
            # Method 2: fresh full flow
            return run_forgot_confirm(phone, code, ua)

        confirmed = await loop.run_in_executor(None, _verify)

        save_ok_user(bot_uid, fb_uid, phone, pw, ck_str, confirmed)
        status_line = "Confirm ✅" if confirmed else "Not confirm ❌"

        await msg.edit_text(
            f"📌 *{status_line}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 `{phone}`\n"
            f"🆔 `{fb_uid}`\n"
            f"🔑 `{pw}`\n"
            f"🎂 `{dob}`",
            parse_mode="Markdown")
        await update.message.reply_text(
            "🏠 আরো বানাবে?", reply_markup=main_keyboard())

    else:
        await show_home(update.message, uid)

# ═══════════════════════════════════════════════════════════════
# CREATE → EXIST CHECK → INFO → FORGOT FLOW → OTP WAIT
# ═══════════════════════════════════════════════════════════════

async def _do_create(update, ctx, uid, phone, pw):
    msg  = await update.message.reply_text(
        f"🔍 *Checking number...*\n📱 `{phone}`\n\n⏳ Please wait...",
        parse_mode="Markdown")
    loop = asyncio.get_event_loop()
    ua   = rand_ua()

    # ── exist check ───────────────────────────────────────────
    exists = await loop.run_in_executor(
        None, check_phone_exists, phone, ua)
    if exists:
        await msg.edit_text(
            f"⚠️ *Number Already Registered!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 `{phone}`\n\n"
            f"❌ এই number এ আগে থেকেই account আছে।\n"
            f"অন্য number দিন।",
            parse_mode="Markdown")
        await update.message.reply_text("🏠", reply_markup=main_keyboard())
        return

    # ── create ────────────────────────────────────────────────
    await msg.edit_text(
        f"✅ *Number OK!*\n📱 `{phone}`\n\n🚀 Creating...",
        parse_mode="Markdown")

    result, fb_uid, ck_str, dob, ua = await loop.run_in_executor(
        None, create_one_ext, uid, phone, pw)

    if result == "checkpoint":
        await msg.edit_text(
            f"⚠️ *CHECKPOINT*\n📱 `{phone}`",
            parse_mode="Markdown")
        await update.message.reply_text("🏠", reply_markup=main_keyboard())
        return
    if result != "ok":
        await msg.edit_text(
            f"❌ *FAILED*\n📱 `{phone}`",
            parse_mode="Markdown")
        await update.message.reply_text("🏠", reply_markup=main_keyboard())
        return

    # ── info দেখাও ────────────────────────────────────────────
    p1 = ck_str[:300]; p2 = ck_str[300:]
    await msg.edit_text(
        f"✅ *Account Created!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 `{phone}`\n"
        f"🆔 `{fb_uid}`\n"
        f"🔑 `{pw}`\n"
        f"🎂 `{dob}`\n\n"
        f"🍪 *Cookie:*\n`{p1}`",
        parse_mode="Markdown")
    if p2:
        await update.message.reply_text(f"`{p2}`", parse_mode="Markdown")

    # ── forgot flow → OTP পাঠাও ──────────────────────────────
    otp_msg = await update.message.reply_text(
        "📨 *Sending OTP via Forgot Password...*",
        parse_mode="Markdown")

    flow, sent = await loop.run_in_executor(
        None, prepare_forgot_flow, phone, ua)

    ctx.user_data["state"] = "wait_otp"
    ctx.user_data["pending_account"] = {
        "flow":    flow,
        "fb_uid":  fb_uid,
        "phone":   phone,
        "pw":      pw,
        "ck_str":  ck_str,
        "dob":     dob,
        "bot_uid": uid,
        "ua":      ua,
    }

    otp_note = ("📩 OTP code পাঠানো হয়েছে — SMS/email চেক করো।"
                if sent else
                "⚠️ Auto OTP send হয়নি — Facebook থেকে আসা code দাও।")

    await otp_msg.edit_text(
        f"{otp_note}\n\n"
        f"🔢 *আপনার OTP code দিন 👇*",
        parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    test_reg_servers()
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
