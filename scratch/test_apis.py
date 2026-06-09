"""
TradSense - API Verification Script
===================================
Script untuk memverifikasi koneksi yfinance, Google Gemini API, dan Telegram Bot.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 console output
if sys.platform.startswith("win"):
    import io
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


async def test_yfinance():
    print("1. Menguji yfinance (Ambil data BBCA.JK)...")
    try:
        import yfinance as yf
        yf.data.YfData.user_agent_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        ticker = yf.Ticker("BBCA.JK")
        df = ticker.history(period="5d")
        if not df.empty:
            print(f"   [OK] yfinance berhasil! Close terakhir BBCA: Rp {df['Close'].iloc[-1]:.0f}")
            return True
        else:
            print("   [ERROR] yfinance mengembalikan DataFrame kosong.")
            return False
    except Exception as e:
        print(f"   [ERROR] yfinance gagal: {e}")
        return False


async def test_gemini():
    print("2. Menguji Google Gemini API...")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("   [ERROR] GEMINI_API_KEY tidak ditemukan di file .env")
        return False

    try:
        from google import genai
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model=model_name,
            contents="Say 'Hello World' in Indonesian",
        )
        print(f"   [OK] Gemini API berhasil! Respon: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"   [ERROR] Gemini API gagal: {e}")
        return False


async def test_telegram():
    print("3. Menguji Telegram Bot...")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("   [ERROR] TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak ditemukan di file .env")
        return False

    try:
        from telegram import Bot
        from telegram.constants import ParseMode
        bot = Bot(token=bot_token)
        test_msg = "🤖 *TradSense Test*\n\nKoneksi bot berhasil dikonfigurasi! ✅"
        await bot.send_message(
            chat_id=chat_id,
            text=test_msg,
            parse_mode=ParseMode.MARKDOWN,
        )
        print("   [OK] Telegram Bot berhasil! Silakan cek chat bot Anda.")
        return True
    except Exception as e:
        print(f"   [ERROR] Telegram Bot gagal: {e}")
        return False


async def main():
    print("=" * 60)
    print("🔍 VERIFIKASI KONEKSI API TRADSENSE")
    print("=" * 60)

    yf_ok = await test_yfinance()
    print("-" * 40)
    gemini_ok = await test_gemini()
    print("-" * 40)
    tg_ok = await test_telegram()

    print("=" * 60)
    if yf_ok and gemini_ok and tg_ok:
        print("🎉 SEMUA KONEKSI API OK & BERFUNGSI DENGAN BAIK!")
    else:
        print("⚠️ BEBERAPA KONEKSI GAGAL. Harap periksa kembali kredensial Anda.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
