# -*- coding: utf-8 -*-
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import sqlite3
import hashlib
from PIL import Image
import pytesseract
import os

# ------------------------------
# LOGGING
# ------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------
# DATABASE SETUP
# ------------------------------
DB_PATH = "pdf_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_name TEXT,
            file_hash TEXT,
            uploader TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ------------------------------
# DUPLICATE / HASH
# ------------------------------
def calculate_file_hash(file_path):
    h = hashlib.sha256()
    with open(file_path,'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def add_file(file_id, file_name, uploader, file_path=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # file hash
    file_hash = calculate_file_hash(file_path) if file_path else None
    # duplicate check
    c.execute("SELECT * FROM files WHERE file_id=? OR file_hash=?", (file_id, file_hash))
    if not c.fetchone():
        c.execute("INSERT INTO files (file_id, file_name, file_hash, uploader) VALUES (?, ?, ?, ?)",
                  (file_id, file_name, file_hash, uploader))
        conn.commit()
        added = True
    else:
        added = False
    conn.close()
    return added

# ------------------------------
# OCR
# ------------------------------
def ocr_from_image(image_path):
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang='aze+eng')
    return text

# ------------------------------
# AI CHAT MODE
# ------------------------------
alchat_users = {}  # user_id : True/False

# ------------------------------
# BOT COMMANDS
# ------------------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Salam! 📚 Mən PDF və sənəd bazası botuyam.\n\n"
        "İstifadə qaydaları:\n"
        "• PDF və ya sənəd göndərin — bazaya əlavə olunur\n"
        "• PDF-i forward edin — bazaya əlavə olunur\n"
        "• Bot qrupa əlavə olunduqda fayllar toplanır\n"
        "• /search söz — fayl adı üzrə axtarış\n"
        "• /stats — baza statistikası\n"
        "• /Alchat — əmrsiz AI/PDF mod aktivləşdirir\n"
        "• /StopAlchat — AI/PDF mod dayandırır"
    )

def handle_document(update: Update, context: CallbackContext):
    doc = update.message.document
    file = doc.get_file()
    file_path = f"temp_{doc.file_name}"
    file.download(file_path)
    added = add_file(doc.file_id, doc.file_name, update.message.from_user.username, file_path)
    os.remove(file_path)
    if added:
        update.message.reply_text(f"✅ '{doc.file_name}' bazaya əlavə edildi!")
    else:
        update.message.reply_text(f"⚠️ '{doc.file_name}' artıq bazada var!")

def search(update: Update, context: CallbackContext):
    query = " ".join(context.args)
    if not query:
        update.message.reply_text("Zəhmət olmasa axtarış sözünü yazın: /search söz")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_name FROM files WHERE file_name LIKE ?", ('%'+query+'%',))
    results = c.fetchall()
    conn.close()
    if not results:
        update.message.reply_text("Heç nə tapılmadı 😔")
    else:
        msg = "Tapılan fayllar:\n" + "\n".join([r[0] for r in results])
        update.message.reply_text(msg)

def stats(update: Update, context: CallbackContext):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM files")
    total = c.fetchone()[0]
    conn.close()
    update.message.reply_text(f"📊 Bazada ümumilikdə {total} sənəd var.")

# ------------------------------
# OCR IMAGE SEARCH
# ------------------------------
def handle_photo(update: Update, context: CallbackContext):
    photo_file = update.message.photo[-1].get_file()
    photo_path = f"temp_image.jpg"
    photo_file.download(photo_path)
    text = ocr_from_image(photo_path)
    os.remove(photo_path)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_name FROM files WHERE file_name LIKE ?", ('%'+text+'%',))
    results = c.fetchall()
    conn.close()
    if results:
        msg = "Tapılan fayllar (OCR əsasında):\n" + "\n".join([r[0] for r in results])
    else:
        msg = "Heç nə tapılmadı, amma AI cavab verə bilər."
    update.message.reply_text(msg)

# ------------------------------
# ALCHAT MODE
# ------------------------------
def alchat_command(update: Update, context: CallbackContext):
    alchat_users[update.message.from_user.id] = True
    update.message.reply_text("🤖 AlChat modu aktivdir! İndi əmrsiz suallar verə bilərsiniz.")

def stop_alchat_command(update: Update, context: CallbackContext):
    alchat_users[update.message.from_user.id] = False
    update.message.reply_text("🛑 AlChat modu dayandırıldı.")

def handle_alchat(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if alchat_users.get(user_id):
        query = update.message.text
        # PDF bazasında axtarış
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT file_name FROM files WHERE file_name LIKE ?", ('%'+query+'%',))
        results = c.fetchall()
        conn.close()
        msg = ""
        if results:
            msg += "Tapılan fayllar:\n" + "\n".join([r[0] for r in results]) + "\n"
        msg += "[AlChat AI]: Sualınıza cavab verə bilirəm."
        update.message.reply_text(msg)

# ------------------------------
# MAIN
# ------------------------------
def main():
    init_db()
    TOKEN = "8640300519:AAHrkRKyyiwpVuhMyuI01_FqCjjqhcCG9Qs"  # Sənin token
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Commandlar
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("search", search))
    dp.add_handler(CommandHandler("stats", stats))
    dp.add_handler(CommandHandler("Alchat", alchat_command))
    dp.add_handler(CommandHandler("StopAlchat", stop_alchat_command))

    # Fayl / şəkil / AI mesajları
    dp.add_handler(MessageHandler(Filters.document, handle_document))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_alchat))

    # Botu işə sal
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
