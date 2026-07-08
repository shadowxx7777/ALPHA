from groq import Groq
from dotenv import load_dotenv
from duckduckgo_search import DDGS
import customtkinter as ctk
import threading
import speech_recognition as sr
import tkinter as tk
from tkinter import filedialog
import os
import datetime
import hashlib
import sqlite3
import asyncio
import edge_tts
import pygame
import tempfile
from PIL import Image
import PIL.ImageDraw
from plyer import notification

# ===== تحميل المفاتيح =====
load_dotenv()
GROQ_CLIENT = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# ===== الألوان =====
COLORS = {
    "bg_main":      "#07070f",
    "bg_header":    "#0a0a14",
    "bg_sidebar":   "#08080f",
    "bg_chat":      "#07070f",
    "bg_user_msg":  "#150a2e",
    "bg_alpha_msg": "#0e0b1a",
    "bg_input":     "#0a0a14",
    "bg_card":      "#0f0c1f",
    "purple_dark":  "#12082e",
    "purple_mid":   "#35186e",
    "purple_light": "#6233b8",
    "purple_glow":  "#4a2490",
    "gold":         "#d4a820",
    "gold_light":   "#f0c840",
    "gold_dim":     "#3a2c08",
    "text_main":    "#e2d9ff",
    "text_sub":     "#6b5f88",
    "border":       "#1e1535",
    "border_gold":  "#3a2e10",
    "red":          "#8b1a1a",
    "red_hover":    "#b22222",
    "green":        "#1a5c2e",
}

# ===== قاعدة البيانات =====
DB_PATH = os.path.join(os.path.expanduser("~"), "OneDrive", "alpha_data.db")
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = os.path.join(os.path.expanduser("~"), "alpha_data.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT,
        language TEXT DEFAULT 'ar', voice_enabled INTEGER DEFAULT 1,
        voice_name TEXT DEFAULT 'ar-EG-SalmaNeural',
        model TEXT DEFAULT 'llama-3.1-8b-instant', created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT,
        created_at TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY, conversation_id INTEGER,
        role TEXT, content TEXT, created_at TEXT)''')
    for col in ["voice_name TEXT DEFAULT 'ar-EG-SalmaNeural'",
                "model TEXT DEFAULT 'llama-3.1-8b-instant'"]:
        try: c.execute(f"ALTER TABLE users ADD COLUMN {col}")
        except: pass
    conn.commit(); conn.close()

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def register_user(u, p):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT INTO users (username,password,created_at) VALUES (?,?,?)",
                  (u, hash_password(p), datetime.datetime.now().isoformat()))
        conn.commit(); conn.close(); return True
    except: return False

def login_user(u, p):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,username,language,voice_enabled,voice_name,model FROM users WHERE username=? AND password=?",
              (u, hash_password(p)))
    r = c.fetchone(); conn.close(); return r

def save_message(cid, role, content):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO messages (conversation_id,role,content,created_at) VALUES (?,?,?,?)",
              (cid, role, content, datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()

def create_conversation(uid, title):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO conversations (user_id,title,created_at,updated_at) VALUES (?,?,?,?)",
              (uid, title, now, now))
    cid = c.lastrowid; conn.commit(); conn.close(); return cid

def get_conversations(uid):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 30", (uid,))
    r = c.fetchall(); conn.close(); return r

def get_messages(cid):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    r = c.fetchall(); conn.close(); return r

def update_conv_time(cid):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (datetime.datetime.now().isoformat(), cid))
    conn.commit(); conn.close()

def delete_conversation(cid):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
    c.execute("DELETE FROM conversations WHERE id=?", (cid,))
    conn.commit(); conn.close()

def update_user_settings(uid, **kw):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    for k, v in kw.items(): c.execute(f"UPDATE users SET {k}=? WHERE id=?", (v, uid))
    conn.commit(); conn.close()

init_db()
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
pygame.mixer.init()

# ===== الحالة =====
current_user = None
current_conv_id = None
messages_history = []
is_listening = False
current_file_path = None
current_language = "ar"
voice_enabled = True
current_voice = "ar-EG-SalmaNeural"
current_model = "llama-3.1-8b-instant"

# ===== اللغات والأصوات =====
LANGUAGES = {
    "ar": "🇸🇦 العربية",
    "en": "🇺🇸 English",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "fr": "🇫🇷 Français",
    "de": "🇩🇪 Deutsch",
    "es": "🇪🇸 Español",
    "tr": "🇹🇷 Türkçe",
}

VOICES = {
    "ar": [("سلمى - مصري ✨", "ar-EG-SalmaNeural"),
           ("زرية - سعودي", "ar-SA-ZariyahNeural"),
           ("فاطمة - إماراتي", "ar-AE-FatimaNeural")],
    "en": [("Aria - أمريكي ✨", "en-US-AriaNeural"),
           ("Jenny - أمريكي", "en-US-JennyNeural"),
           ("Sonia - بريطاني", "en-GB-SoniaNeural")],
    "ja": [("Nanami ✨", "ja-JP-NanamiNeural"),
           ("Aoi", "ja-JP-AoiNeural")],
    "ko": [("SunHi ✨", "ko-KR-SunHiNeural"),
           ("Yuna", "ko-KR-YunaNeural")],
    "fr": [("Denise ✨", "fr-FR-DeniseNeural"),
           ("Eloise", "fr-FR-EloiseNeural")],
    "de": [("Katja ✨", "de-DE-KatjaNeural"),
           ("Amala", "de-DE-AmalaNeural")],
    "es": [("Elvira ✨", "es-ES-ElviraNeural"),
           ("Abril", "es-MX-DalilaNeural")],
    "tr": [("Emel ✨", "tr-TR-EmelNeural")],
}

SPEECH_LANGS = {
    "ar": "ar-SA", "en": "en-US", "ja": "ja-JP",
    "ko": "ko-KR", "fr": "fr-FR", "de": "de-DE",
    "es": "es-ES", "tr": "tr-TR",
}

# ===== System Prompts =====
SYSTEM_PROMPTS = {
    "ar": """أنتِ ألفا، مساعدة ذكاء اصطناعي متقدمة أنشأها Shadow.
قواعد صارمة جداً:
- تحدثي دائماً بالعربية الفصحى السليمة بدون أي أخطاء إملائية أو نحوية
- اذهبي مباشرة للإجابة بدون مقدمات
- أجيبي بدقة عالية — إذا لم تعرفي الإجابة قولي ذلك
- لا تقولي "بالطبع" أو "بالتأكيد" في بداية كل رد
- إذا بحثت في الإنترنت استخدمي النتائج بدقة""",
    "en": """You are Alpha, an advanced AI assistant created by Shadow.
Strict rules:
- Always respond in perfect English with no grammatical errors
- Be direct and accurate — no unnecessary filler
- If you don't know something, say so honestly
- Use search results accurately when provided""",
    "ja": """あなたはAlphaです。Shadowが作った高度なAIアシスタントです。
ルール：
- 常に正確な日本語で答えてください
- 直接的に答えてください
- わからない場合は正直に言ってください""",
    "ko": """당신은 Shadow가 만든 AI 어시스턴트 Alpha입니다.
규칙: 항상 정확한 한국어로 답하세요. 직접적으로 답하세요.""",
    "fr": """Tu es Alpha, une assistante IA créée par Shadow.
Règles: Réponds toujours en français parfait. Sois directe et précise.""",
    "de": """Du bist Alpha, eine KI-Assistentin von Shadow.
Regeln: Antworte immer auf perfektem Deutsch. Sei direkt und präzise.""",
    "es": """Eres Alpha, una asistente de IA creada por Shadow.
Reglas: Responde siempre en español perfecto. Sé directa y precisa.""",
    "tr": """Sen Shadow tarafından oluşturulan Alpha adlı bir yapay zeka asistanısın.
Kurallar: Her zaman mükemmel Türkçe ile cevap ver. Doğrudan ve kesin ol.""",
}

def T(key):
    TEXTS = {
        "ar": {
            "title": "✦ ألفا ✦", "subtitle": "مساعدتك الذكية",
            "welcome_title": "مرحباً! أنا ألفا 👧",
            "welcome_sub": "محادثة • تحليل الصور • بحث الإنترنت • 8 لغات",
            "placeholder": "اكتب رسالتك...", "send": "إرسال ➤",
            "voice": "🎤 صوت", "listening": "🔴 أستمع...",
            "clear": "🗑️ مسح", "new_chat": "+ محادثة جديدة",
            "settings": "⚙️ الإعدادات", "logout": "⬅️ خروج",
            "you": "أنت", "alpha": "ألفا 👧", "thinking": "ألفا تفكر ✦",
            "searching": "ألفا تبحث 🌐", "history": "المحادثات",
            "login_title": "تسجيل الدخول", "register_title": "إنشاء حساب",
            "username": "اسم المستخدم", "password": "كلمة المرور",
            "login_btn": "دخول", "register_btn": "إنشاء حساب",
            "switch_register": "ليس لديك حساب؟ سجّل",
            "switch_login": "لديك حساب؟ سجّل دخول",
            "error_login": "اسم المستخدم أو كلمة المرور غير صحيحة",
            "error_register": "اسم المستخدم مستخدم بالفعل",
            "success_register": "تم إنشاء الحساب! سجّل دخولك",
            "settings_title": "⚙️ الإعدادات",
            "lang_label": "اللغة", "voice_label": "الصوت",
            "voice_on": "تفعيل الصوت", "model_label": "الموديل",
            "save": "💾 حفظ", "no_convs": "لا توجد محادثات",
        },
        "en": {
            "title": "✦ Alpha AI ✦", "subtitle": "Your Smart Assistant",
            "welcome_title": "Hello! I'm Alpha 👧",
            "welcome_sub": "Chat • Image Analysis • Web Search • 8 Languages",
            "placeholder": "Type your message...", "send": "Send ➤",
            "voice": "🎤 Voice", "listening": "🔴 Listening...",
            "clear": "🗑️ Clear", "new_chat": "+ New Chat",
            "settings": "⚙️ Settings", "logout": "⬅️ Logout",
            "you": "You", "alpha": "Alpha 👧", "thinking": "Alpha is thinking ✦",
            "searching": "Alpha is searching 🌐", "history": "Conversations",
            "login_title": "Login", "register_title": "Create Account",
            "username": "Username", "password": "Password",
            "login_btn": "Login", "register_btn": "Register",
            "switch_register": "No account? Register",
            "switch_login": "Have account? Login",
            "error_login": "Wrong username or password",
            "error_register": "Username already taken",
            "success_register": "Account created! Please login",
            "settings_title": "⚙️ Settings",
            "lang_label": "Language", "voice_label": "Voice",
            "voice_on": "Enable Voice", "model_label": "Model",
            "save": "💾 Save", "no_convs": "No conversations yet",
        },
    }
    lang = current_language if current_language in TEXTS else "en"
    return TEXTS[lang].get(key, TEXTS["en"].get(key, key))

def get_system_prompt():
    return SYSTEM_PROMPTS.get(current_language, SYSTEM_PROMPTS["en"])

# ===== بحث الإنترنت =====
def search_web(query, max_results=3):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if results:
                return "\n".join([f"- {r['title']}: {r['body']}" for r in results])
    except Exception as e:
        print(f"Search error: {e}")
    return ""

def needs_search(text):
    keywords = [
        "كم", "متى", "من هو", "ما هو", "ما هي", "أين", "كيف",
        "عدد", "تاريخ", "حكم", "سعر", "آخر", "أحدث", "الآن",
        "how many", "when", "who is", "what is", "where", "price",
        "latest", "current", "today", "now"
    ]
    return any(k in text.lower() for k in keywords)

# ===== الصوت =====
def speak_edge(text):
    if not voice_enabled: return
    def _speak():
        try:
            async def _async():
                tts = edge_tts.Communicate(text, current_voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    tmp = f.name
                await tts.save(tmp)
                pygame.mixer.music.load(tmp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                try: os.unlink(tmp)
                except: pass
            asyncio.run(_async())
        except Exception as e:
            print(f"TTS Error: {e}")
    threading.Thread(target=_speak, daemon=True).start()

# ===== إشعارات =====
def send_notification(title, message):
    try:
        notification.notify(
            title=title, message=message,
            app_name="Alpha AI", timeout=4
        )
    except: pass

# ===== شاشة الدخول =====
def show_login_screen():
    win = ctk.CTk()
    win.title("Alpha AI")
    win.geometry("440x620")
    win.resizable(False, False)
    win.configure(fg_color=COLORS["bg_main"])

    is_reg = [False]

    card = ctk.CTkFrame(win, fg_color=COLORS["bg_card"], corner_radius=24,
                        border_width=1, border_color=COLORS["gold_dim"])
    card.pack(fill="both", expand=True, padx=35, pady=35)

    # صورة ألفا
    av = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_avatar.jpg")
    if os.path.exists(av):
        img = Image.open(av).resize((100, 100)).convert("RGBA")
        mask = Image.new("L", (100, 100), 0)
        PIL.ImageDraw.Draw(mask).ellipse((0, 0, 100, 100), fill=255)
        img.putalpha(mask)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(100, 100))
        ctk.CTkLabel(card, image=ctk_img, text="").pack(pady=(24, 4))
    else:
        ctk.CTkLabel(card, text="✦", font=("Arial", 44), text_color=COLORS["gold"]).pack(pady=(28, 0))

    ctk.CTkLabel(card, text="Alpha AI", font=("Arial", 28, "bold"),
                 text_color=COLORS["purple_light"]).pack()
    ctk.CTkLabel(card, text="Powered by Shadow", font=("Arial", 11),
                 text_color=COLORS["text_sub"]).pack(pady=(0, 15))
    ctk.CTkFrame(card, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x", padx=25, pady=(0, 15))

    title_lbl = ctk.CTkLabel(card, text=T("login_title"), font=("Arial", 16, "bold"),
                              text_color=COLORS["text_main"])
    title_lbl.pack(pady=(0, 10))

    uentry = ctk.CTkEntry(card, placeholder_text=T("username"), font=("Arial", 13),
                          height=46, width=300, fg_color=COLORS["bg_main"],
                          border_color=COLORS["purple_dark"], text_color=COLORS["text_main"],
                          corner_radius=12)
    uentry.pack(pady=5)

    pentry = ctk.CTkEntry(card, placeholder_text=T("password"), show="•",
                          font=("Arial", 13), height=46, width=300,
                          fg_color=COLORS["bg_main"], border_color=COLORS["purple_dark"],
                          text_color=COLORS["text_main"], corner_radius=12)
    pentry.pack(pady=5)

    msg_lbl = ctk.CTkLabel(card, text="", font=("Arial", 12), text_color=COLORS["red_hover"])
    msg_lbl.pack(pady=4)

    def do_action():
        global current_user, current_language, voice_enabled, current_voice, current_model
        u = uentry.get().strip(); p = pentry.get().strip()
        if not u or not p:
            msg_lbl.configure(text="⚠️ أدخل البيانات"); return
        if is_reg[0]:
            # Shadow محظور 😌
            if 'shadow' in u.lower():
                msg_lbl.configure(text="⛔ هذا الاسم محجوز ولا يمكن استخدامه!", text_color=COLORS["red_hover"])
                return
            if register_user(u, p):
                msg_lbl.configure(text="✅ " + T("success_register"), text_color="#27ae60")
                is_reg[0] = False
                title_lbl.configure(text=T("login_title"))
                act_btn.configure(text=T("login_btn"))
                sw_btn.configure(text=T("switch_register"))
            else:
                msg_lbl.configure(text="❌ " + T("error_register"))
        else:
            user = login_user(u, p)
            if user:
                current_user = {"id": user[0], "username": user[1]}
                current_language = user[2] or "ar"
                voice_enabled = bool(user[3]) if user[3] is not None else True
                current_voice = user[4] or "ar-EG-SalmaNeural"
                current_model = user[5] or "llama-3.1-8b-instant"
                win.destroy()
                show_main_app()
            else:
                msg_lbl.configure(text="❌ " + T("error_login"))

    def toggle():
        is_reg[0] = not is_reg[0]
        if is_reg[0]:
            title_lbl.configure(text=T("register_title"))
            act_btn.configure(text=T("register_btn"))
            sw_btn.configure(text=T("switch_login"))
        else:
            title_lbl.configure(text=T("login_title"))
            act_btn.configure(text=T("login_btn"))
            sw_btn.configure(text=T("switch_register"))
        msg_lbl.configure(text="")

    act_btn = ctk.CTkButton(card, text=T("login_btn"), command=do_action,
                             width=300, height=46, font=("Arial", 14, "bold"),
                             fg_color=COLORS["purple_mid"], hover_color=COLORS["purple_light"],
                             corner_radius=12)
    act_btn.pack(pady=10)

    sw_btn = ctk.CTkButton(card, text=T("switch_register"), command=toggle,
                            width=300, height=34, font=("Arial", 12),
                            fg_color="transparent", hover_color=COLORS["bg_main"],
                            text_color=COLORS["gold"])
    sw_btn.pack()

    win.bind("<Return>", lambda e: do_action())
    win.mainloop()

# ===== التطبيق الرئيسي =====
def show_main_app():
    global app, chat_frame, canvas, entry, mic_btn, image_label, send_btn

    app = ctk.CTk()
    app.title("Alpha AI 👧")
    app.geometry("1150x780")
    app.minsize(900, 600)
    app.configure(fg_color=COLORS["bg_main"])

    main = ctk.CTkFrame(app, fg_color=COLORS["bg_main"])
    main.pack(fill="both", expand=True)

    # ===== الشريط الجانبي =====
    sidebar = ctk.CTkFrame(main, fg_color=COLORS["bg_sidebar"], width=250,
                            corner_radius=0, border_width=1, border_color=COLORS["border"])
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    # شعار
    logo = ctk.CTkFrame(sidebar, fg_color="transparent", height=95)
    logo.pack(fill="x"); logo.pack_propagate(False)
    ctk.CTkLabel(logo, text="✦ Alpha AI ✦", font=("Arial", 18, "bold"),
                 text_color=COLORS["gold"]).pack(pady=(18, 2))
    ctk.CTkLabel(logo, text=f"👤 {current_user['username']}", font=("Arial", 11),
                 text_color=COLORS["text_sub"]).pack()

    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x", padx=12, pady=5)

    def new_chat():
        global current_conv_id, messages_history, current_file_path
        current_conv_id = None; messages_history = []; current_file_path = None
        for w in chat_frame.winfo_children(): w.destroy()
        show_welcome(); refresh_history()
        image_label.configure(text="")

    ctk.CTkButton(sidebar, text=T("new_chat"), command=new_chat,
                  fg_color=COLORS["purple_dark"], hover_color=COLORS["purple_mid"],
                  font=("Arial", 13, "bold"), height=42, corner_radius=22,
                  border_width=1, border_color=COLORS["gold_dim"]).pack(fill="x", padx=12, pady=6)

    ctk.CTkLabel(sidebar, text=T("history"), font=("Arial", 11, "bold"),
                 text_color=COLORS["text_sub"]).pack(anchor="w", padx=15, pady=(6, 2))

    hist_scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
    hist_scroll.pack(fill="both", expand=True, padx=5)

    def refresh_history():
        for w in hist_scroll.winfo_children(): w.destroy()
        convs = get_conversations(current_user["id"])
        if not convs:
            ctk.CTkLabel(hist_scroll, text=T("no_convs"), font=("Arial", 11),
                         text_color=COLORS["text_sub"]).pack(pady=10); return
        for conv in convs:
            row = ctk.CTkFrame(hist_scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)

            def load(cid=conv[0]):
                global current_conv_id, messages_history
                current_conv_id = cid; messages_history = []
                for w in chat_frame.winfo_children(): w.destroy()
                for role, content in get_messages(cid):
                    s = T("you") if role == "user" else T("alpha")
                    add_message(s, content, "user" if role == "user" else "alpha")
                    messages_history.append({"role": role, "content": content})

            def delete(cid=conv[0]):
                global current_conv_id, messages_history
                delete_conversation(cid)
                if current_conv_id == cid:
                    current_conv_id = None; messages_history = []
                    for w in chat_frame.winfo_children(): w.destroy()
                    show_welcome()
                refresh_history()

            ctk.CTkButton(row, text=conv[1][:26]+("…" if len(conv[1])>26 else ""),
                          command=load, fg_color="transparent",
                          hover_color=COLORS["bg_card"], anchor="w",
                          font=("Arial", 12), text_color=COLORS["text_main"],
                          height=34).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="🗑", command=delete, width=28, height=28,
                          fg_color="transparent", hover_color=COLORS["red"],
                          font=("Arial", 11), text_color=COLORS["text_sub"]).pack(side="right")

    refresh_history()
    ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x", padx=12, pady=4)

    # ===== الإعدادات =====
    def show_settings():
        global current_language, voice_enabled, current_voice, current_model
        sw = ctk.CTkToplevel(app)
        sw.title(T("settings_title"))
        sw.geometry("440x580")
        sw.configure(fg_color=COLORS["bg_main"])
        sw.grab_set()

        sf = ctk.CTkFrame(sw, fg_color=COLORS["bg_card"], corner_radius=20,
                          border_width=1, border_color=COLORS["gold_dim"])
        sf.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(sf, text=T("settings_title"), font=("Arial", 18, "bold"),
                     text_color=COLORS["gold"]).pack(pady=(20, 5))
        ctk.CTkFrame(sf, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x", padx=20, pady=6)

        # اللغة
        ctk.CTkLabel(sf, text=T("lang_label"), font=("Arial", 13, "bold"),
                     text_color=COLORS["text_main"]).pack(anchor="w", padx=20, pady=(10, 2))
        lang_var = ctk.StringVar(value=current_language)
        lang_values = list(LANGUAGES.keys())
        lang_display = [LANGUAGES[l] for l in lang_values]

        lang_menu = ctk.CTkOptionMenu(sf, values=lang_display, variable=ctk.StringVar(value=LANGUAGES[current_language]),
                                       fg_color=COLORS["purple_dark"], button_color=COLORS["purple_mid"],
                                       font=("Arial", 12))
        lang_menu.pack(padx=20, pady=4, fill="x")

        # الصوت
        ctk.CTkLabel(sf, text=T("voice_label"), font=("Arial", 13, "bold"),
                     text_color=COLORS["text_main"]).pack(anchor="w", padx=20, pady=(10, 2))

        vs_var = ctk.BooleanVar(value=voice_enabled)
        ctk.CTkSwitch(sf, text=T("voice_on"), variable=vs_var,
                      progress_color=COLORS["purple_mid"],
                      font=("Arial", 12), text_color=COLORS["text_main"]).pack(anchor="w", padx=20)

        lang_key = current_language if current_language in VOICES else "ar"
        v_opts = [v[0] for v in VOICES[lang_key]]
        v_vals = [v[1] for v in VOICES[lang_key]]
        cur_vname = v_opts[0]
        for i, v in enumerate(v_vals):
            if v == current_voice: cur_vname = v_opts[i]; break

        voice_var = ctk.StringVar(value=cur_vname)
        voice_menu = ctk.CTkOptionMenu(sf, values=v_opts, variable=voice_var,
                                        fg_color=COLORS["purple_dark"], button_color=COLORS["purple_mid"],
                                        font=("Arial", 12))
        voice_menu.pack(padx=20, pady=6, fill="x")

        # الموديل
        ctk.CTkLabel(sf, text=T("model_label"), font=("Arial", 13, "bold"),
                     text_color=COLORS["text_main"]).pack(anchor="w", padx=20, pady=(10, 2))
        model_var = ctk.StringVar(value=current_model)
        ctk.CTkOptionMenu(sf, values=["llama-3.1-8b-instant", "llama-3.3-70b-versatile",
                                       "mixtral-8x7b-32768", "gemma2-9b-it"],
                           variable=model_var, fg_color=COLORS["purple_dark"],
                           button_color=COLORS["purple_mid"],
                           font=("Arial", 12)).pack(padx=20, pady=4, fill="x")

        def save_s():
            global current_language, voice_enabled, current_voice, current_model
            sel_lang_display = lang_menu.get()
            for k, v in LANGUAGES.items():
                if v == sel_lang_display: current_language = k; break
            voice_enabled = vs_var.get()
            sel_vname = voice_var.get()
            lk = current_language if current_language in VOICES else "ar"
            for name, val in VOICES[lk]:
                if name == sel_vname: current_voice = val; break
            current_model = model_var.get()
            update_user_settings(current_user["id"],
                                 language=current_language,
                                 voice_enabled=1 if voice_enabled else 0,
                                 voice_name=current_voice, model=current_model)
            sw.destroy()
            app.destroy()
            show_main_app()

        # ===== معلومات التواصل =====
        ctk.CTkFrame(sf, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x", padx=20, pady=(10,5))
        
        contact_frame = ctk.CTkFrame(sf, fg_color=COLORS["bg_main"], corner_radius=10)
        contact_frame.pack(fill="x", padx=20, pady=(0,8))
        
        ctk.CTkLabel(contact_frame, text="📞 تواصل معنا", font=("Arial", 12, "bold"),
                     text_color=COLORS["gold"]).pack(anchor="w", padx=12, pady=(8,2))
        ctk.CTkLabel(contact_frame, text="📸 Instagram: shadow.____.7",
                     font=("Arial", 11), text_color=COLORS["text_sub"]).pack(anchor="w", padx=12)
        ctk.CTkLabel(contact_frame, text="🐛 الإبلاغ عن الأخطاء والمساعدة",
                     font=("Arial", 10), text_color=COLORS["text_sub"]).pack(anchor="w", padx=12, pady=(0,8))

        ctk.CTkButton(sf, text=T("save"), command=save_s,
                      fg_color=COLORS["purple_mid"], hover_color=COLORS["purple_light"],
                      height=44, font=("Arial", 14, "bold"), corner_radius=12).pack(padx=20, pady=(5,16), fill="x")

    ctk.CTkButton(sidebar, text=T("settings"), command=show_settings,
                  fg_color="transparent", hover_color=COLORS["bg_card"],
                  font=("Arial", 12), text_color=COLORS["text_sub"], height=36).pack(fill="x", padx=10, pady=2)

    def do_logout():
        app.destroy(); show_login_screen()

    ctk.CTkButton(sidebar, text=T("logout"), command=do_logout,
                  fg_color="transparent", hover_color=COLORS["red"],
                  font=("Arial", 12), text_color=COLORS["text_sub"], height=36).pack(fill="x", padx=10, pady=(2,12))

    # ===== المنطقة الرئيسية =====
    right = ctk.CTkFrame(main, fg_color=COLORS["bg_main"])
    right.pack(side="left", fill="both", expand=True)

    # هيدر
    header = ctk.CTkFrame(right, fg_color=COLORS["bg_header"], height=62,
                           corner_radius=0, border_width=1, border_color=COLORS["border"])
    header.pack(fill="x"); header.pack_propagate(False)

    av2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_avatar.jpg")
    if os.path.exists(av2):
        img2 = Image.open(av2).resize((44, 44)).convert("RGBA")
        mask2 = Image.new("L", (44, 44), 0)
        PIL.ImageDraw.Draw(mask2).ellipse((0, 0, 44, 44), fill=255)
        img2.putalpha(mask2)
        ctk_img2 = ctk.CTkImage(light_image=img2, dark_image=img2, size=(44, 44))
        ctk.CTkLabel(header, image=ctk_img2, text="").pack(side="left", padx=(15, 5), pady=9)

    ctk.CTkLabel(header, text=T("title"), font=("Arial", 20, "bold"),
                 text_color=COLORS["gold"]).pack(side="left", padx=5, pady=15)
    ctk.CTkLabel(header, text=T("subtitle"), font=("Arial", 12),
                 text_color=COLORS["text_sub"]).pack(side="left", pady=15)

    def clear_chat():
        global messages_history, current_conv_id
        messages_history = []; current_conv_id = None
        for w in chat_frame.winfo_children(): w.destroy()
        show_welcome()

    ctk.CTkButton(header, text=T("clear"), command=clear_chat,
                  width=85, fg_color=COLORS["red"], hover_color=COLORS["red_hover"],
                  height=36, corner_radius=10).pack(side="right", padx=12, pady=13)

    ctk.CTkFrame(right, height=2, fg_color=COLORS["gold"]).pack(fill="x")

    # منطقة المحادثة
    chat_con = ctk.CTkFrame(right, fg_color=COLORS["bg_chat"])
    chat_con.pack(fill="both", expand=True)

    canvas = tk.Canvas(chat_con, bg=COLORS["bg_chat"], highlightthickness=0)
    scrollbar = ctk.CTkScrollbar(chat_con, command=canvas.yview,
                                  button_color=COLORS["purple_dark"],
                                  button_hover_color=COLORS["purple_mid"])
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    chat_frame = ctk.CTkFrame(canvas, fg_color=COLORS["bg_chat"])
    cw = canvas.create_window((0, 0), window=chat_frame, anchor="nw")

    def on_fc(e): canvas.configure(scrollregion=canvas.bbox("all"))
    def on_cc(e): canvas.itemconfig(cw, width=e.width)
    chat_frame.bind("<Configure>", on_fc)
    canvas.bind("<Configure>", on_cc)
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def show_welcome():
        wf = ctk.CTkFrame(chat_frame, fg_color=COLORS["bg_card"], corner_radius=22,
                          border_width=1, border_color=COLORS["border_gold"])
        wf.pack(fill="x", padx=50, pady=50)

        avp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_avatar.jpg")
        if os.path.exists(avp):
            avi = Image.open(avp).resize((80, 80)).convert("RGBA")
            avm = Image.new("L", (80, 80), 0)
            PIL.ImageDraw.Draw(avm).ellipse((0, 0, 80, 80), fill=255)
            avi.putalpha(avm)
            avctk = ctk.CTkImage(light_image=avi, dark_image=avi, size=(80, 80))
            ctk.CTkLabel(wf, image=avctk, text="").pack(pady=(24, 4))
        else:
            ctk.CTkLabel(wf, text="✦", font=("Arial", 36), text_color=COLORS["gold"]).pack(pady=(24, 0))

        ctk.CTkLabel(wf, text=T("welcome_title"), font=("Arial", 22, "bold"),
                     text_color=COLORS["purple_light"]).pack(pady=6)
        ctk.CTkLabel(wf, text=T("welcome_sub"), font=("Arial", 13),
                     text_color=COLORS["text_sub"], justify="center").pack(pady=(0, 24))

    show_welcome()

    def add_message(sender, text, msg_type):
        is_user = msg_type == "user"
        outer = ctk.CTkFrame(chat_frame, fg_color="transparent")
        outer.pack(fill="x", padx=18, pady=5)
        bubble = ctk.CTkFrame(outer,
                              fg_color=COLORS["bg_user_msg"] if is_user else COLORS["bg_alpha_msg"],
                              corner_radius=18, border_width=1,
                              border_color=COLORS["purple_dark"] if is_user else COLORS["border"])
        bubble.pack(side="right" if is_user else "left")
        ctk.CTkLabel(bubble, text=sender, font=("Arial", 10, "bold"),
                     text_color=COLORS["gold"] if is_user else COLORS["purple_light"]
                     ).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(bubble, text=text, font=("Arial", 13),
                     wraplength=580, justify="left", text_color=COLORS["text_main"]
                     ).pack(anchor="w", padx=14, pady=(3, 12))
        canvas.update_idletasks()
        canvas.yview_moveto(1.0)

    def update_last(sender, text):
        ch = chat_frame.winfo_children()
        if ch: ch[-1].destroy()
        outer = ctk.CTkFrame(chat_frame, fg_color="transparent")
        outer.pack(fill="x", padx=18, pady=5)
        bubble = ctk.CTkFrame(outer, fg_color=COLORS["bg_alpha_msg"],
                              corner_radius=18, border_width=1, border_color=COLORS["border"])
        bubble.pack(side="left")
        ctk.CTkLabel(bubble, text=sender, font=("Arial", 10, "bold"),
                     text_color=COLORS["purple_light"]).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(bubble, text=text, font=("Arial", 13),
                     wraplength=580, justify="left", text_color=COLORS["text_main"]
                     ).pack(anchor="w", padx=14, pady=(3, 12))
        canvas.update_idletasks()
        canvas.yview_moveto(1.0)

    # ===== إرسال =====
    def send_message(user_text=None):
        global current_conv_id, current_file_path, messages_history

        if user_text is None:
            user_text = entry.get().strip()
        if not user_text and not current_file_path:
            return

        entry.delete(0, "end")

        if current_conv_id is None:
            title = user_text[:30] if user_text else "محادثة"
            current_conv_id = create_conversation(current_user["id"], title)
            refresh_history()

        display = user_text
        if current_file_path:
            display = (user_text+"\n" if user_text else "") + f"[📎 {os.path.basename(current_file_path)}]"

        add_message(T("you"), display, "user")
        save_message(current_conv_id, "user", display)
        messages_history.append({"role": "user", "content": display})

        ext = os.path.splitext(current_file_path)[1].lower() if current_file_path else ""
        is_image = current_file_path and ext in [".png",".jpg",".jpeg",".webp",".bmp"]

        file_path_copy = current_file_path
        current_file_path = None
        image_label.configure(text="")

        add_message(T("alpha"), T("thinking"), "alpha")

        def get_response():
            global current_conv_id
            try:
                hist = [m for m in messages_history if "images" not in m]

                # بحث إنترنت
                search_results = ""
                if needs_search(user_text) and not is_image:
                    chat_frame.after(0, lambda: update_last(T("alpha"), T("searching")))
                    search_results = search_web(user_text)

                # تجهيز الرسالة
                if is_image:
                    import base64
                    with open(file_path_copy, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode()
                    ext_map = {".jpg":"jpeg",".jpeg":"jpeg",".png":"png",".webp":"webp",".bmp":"bmp"}
                    mime = ext_map.get(ext, "jpeg")
                    last_msg = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text or "حلل هذه الصورة بالتفصيل"},
                            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img_b64}"}}
                        ]
                    }
                    model_use = "meta-llama/llama-4-scout-17b-16e-instruct"
                elif file_path_copy and ext == ".txt":
                    with open(file_path_copy, "r", encoding="utf-8", errors="ignore") as f:
                        fc = f.read()
                    last_msg = {"role": "user", "content": f"{user_text}\n\nمحتوى الملف:\n{fc[:3000]}"}
                    model_use = current_model
                else:
                    content = user_text
                    if search_results:
                        content = f"{user_text}\n\nنتائج البحث:\n{search_results}\n\nأجب بناءً على هذه النتائج بدقة."
                    last_msg = {"role": "user", "content": content}
                    model_use = current_model

                msgs = [{"role": "system", "content": get_system_prompt()}] + hist[-8:] 
                msgs[-1] = last_msg

                response = GROQ_CLIENT.chat.completions.create(
                    model=model_use,
                    messages=msgs,
                    max_tokens=1024,
                    temperature=0.5,
                )
                reply = response.choices[0].message.content
                messages_history.append({"role": "assistant", "content": reply})
                save_message(current_conv_id, "assistant", reply)
                update_conv_time(current_conv_id)
                chat_frame.after(0, lambda: update_last(T("alpha"), reply))
                speak_edge(reply)
                # إشعار
                send_notification("Alpha AI 👧", reply[:80] + "..." if len(reply) > 80 else reply)

            except Exception as e:
                err = f"⚠️ خطأ: {str(e)}"
                chat_frame.after(0, lambda: update_last(T("alpha"), err))

        threading.Thread(target=get_response, daemon=True).start()

    # ===== استماع =====
    def listen():
        global is_listening
        if is_listening: return
        is_listening = True
        mic_btn.configure(text=T("listening"))

        def _listen():
            global is_listening
            try:
                r = sr.Recognizer()
                with sr.Microphone() as src:
                    r.adjust_for_ambient_noise(src, duration=0.5)
                    audio = r.listen(src, timeout=6)
                    lang_code = SPEECH_LANGS.get(current_language, "ar-SA")
                    text = r.recognize_google(audio, language=lang_code)
                    entry.delete(0, "end")
                    entry.insert(0, text)
                    send_message()
            except Exception:
                pass
            finally:
                is_listening = False
                mic_btn.after(0, lambda: mic_btn.configure(text=T("voice")))

        threading.Thread(target=_listen, daemon=True).start()

    def choose_file():
        global current_file_path
        path = filedialog.askopenfilename(
            filetypes=[("All", "*.png *.jpg *.jpeg *.webp *.bmp *.txt"),
                       ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                       ("Text", "*.txt")])
        if path:
            current_file_path = path
            image_label.configure(text=f"📎 {os.path.basename(path)}")

    # ===== شريط الإدخال =====
    ctk.CTkFrame(right, height=1, fg_color=COLORS["gold_dim"]).pack(fill="x")

    image_label = ctk.CTkLabel(right, text="", font=("Arial", 11), text_color=COLORS["gold"])
    image_label.pack(anchor="w", padx=16, pady=(4, 0))

    input_frame = ctk.CTkFrame(right, fg_color=COLORS["bg_input"], height=76, corner_radius=0)
    input_frame.pack(fill="x", side="bottom")
    input_frame.pack_propagate(False)

    ctk.CTkButton(input_frame, text="📎", command=choose_file,
                  width=44, height=44, fg_color=COLORS["purple_dark"],
                  hover_color=COLORS["purple_mid"], corner_radius=12,
                  font=("Arial", 17)).pack(side="left", padx=(14, 5), pady=16)

    mic_btn = ctk.CTkButton(input_frame, text=T("voice"), command=listen,
                             width=95, height=44, fg_color=COLORS["bg_card"],
                             hover_color=COLORS["purple_dark"], corner_radius=12,
                             font=("Arial", 12), text_color=COLORS["text_main"],
                             border_width=1, border_color=COLORS["border"])
    mic_btn.pack(side="left", padx=5, pady=16)

    entry = ctk.CTkEntry(input_frame, font=("Arial", 14),
                          placeholder_text=T("placeholder"), height=44,
                          fg_color=COLORS["bg_card"], border_color=COLORS["purple_dark"],
                          text_color=COLORS["text_main"],
                          placeholder_text_color=COLORS["text_sub"], corner_radius=12)
    entry.pack(side="left", fill="x", expand=True, padx=5, pady=16)
    entry.bind("<Return>", lambda e: send_message())
    entry.focus()

    send_btn = ctk.CTkButton(input_frame, text=T("send"), command=send_message,
                              width=110, height=44, font=("Arial", 13, "bold"),
                              fg_color=COLORS["purple_mid"], hover_color=COLORS["purple_light"],
                              corner_radius=22, border_width=1, border_color=COLORS["gold_dim"])
    send_btn.pack(side="left", padx=(5, 14), pady=16)

    app.mainloop()

show_login_screen()
