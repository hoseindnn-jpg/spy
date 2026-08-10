import requests
import os
from config import BOT_TOKEN, BASE_URL

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """ارسال پیام به تلگرام"""
    url = f"{BASE_URL}/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def edit_message_reply_markup(chat_id, message_id, reply_markup=None):
    """ویرایش کیبورد یک پیام"""
    url = f"{BASE_URL}/bot{BOT_TOKEN}/editMessageReplyMarkup"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error editing reply markup: {e}")
        return None

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    """پاسخ به دکمه‌های شیشه‌ای (Callback)"""
    url = f"{BASE_URL}/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error answering callback: {e}")

def set_webhook(webhook_url):
    """تنظیم وب‌هوک برای ربات (فقط یک بار در زمان دیپلوی)"""
    url = f"{BASE_URL}/bot{BOT_TOKEN}/setWebhook"
    payload = {"url": webhook_url}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return None

def delete_message(chat_id, message_id):
    """حذف پیام"""
    url = f"{BASE_URL}/bot{BOT_TOKEN}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error deleting message: {e}")
