import requests
import os
import random
import json
import qrcode
import io
import threading
import time
import base64
from queue import Queue
from urllib.parse import unquote, urlparse

# --- تنظیمات اصلی ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

# --- منابع پروکسی‌ها ---
V2RAY_SOURCES = [
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vmess.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vless.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/trojan.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/ss.txt"
]

def parse_config(config_str):
    """نام و آدرس سرور را از کانفیگ‌های مختلف استخراج می‌کند."""
    try:
        protocol = config_str.split("://")[0]
        name = "نامشخص"
        if "#" in config_str:
            name = unquote(config_str.split("#")[-1])

        address = ""
        # استخراج آدرس سرور برای پروتکل‌های مختلف
        if protocol == "vmess":
            try:
                vmess_json_str = base64.b64decode(config_str.split("://")[1].split("#")[0]).decode('utf-8')
                address = json.loads(vmess_json_str).get("add", "")
            except Exception:
                pass # اگر دیکود نشد، روش بعدی را امتحان می‌کند
        
        if not address:
            # برای VLESS, Trojan, SS و فرمت‌های دیگر VMESS
            parsed_url = urlparse(config_str)
            address = parsed_url.hostname
            # در کانفیگ‌های SS، آدرس قبل از @ قرار دارد
            if not address and "@" in parsed_url.path:
                address = parsed_url.path.split("@")[1].split(":")[0]

        return {"protocol": protocol.upper(), "name": name, "address": address, "config": config_str}
    except Exception as e:
        print(f"Error parsing config '{config_str[:30]}...': {e}")
        return None

def test_config_latency(config_info, result_queue, timeout=2.5):
    """سلامت سرور را با یک درخواست وب سبک تست می‌کند."""
    if not config_info or not config_info.get("address"):
        return
    address = config_info["address"]
    test_url = f"https://{address}/generate_204"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        start_time = time.time()
        requests.get(test_url, timeout=timeout, headers=headers, verify=False)
        end_time = time.time()
        latency = int((end_time - start_time) * 1000)
        result_queue.put((latency, config_info))
    except requests.exceptions.RequestException:
        pass

def generate_qr_code(text):
    """یک تصویر کد QR تولید کرده و در حافظه نگه می‌دارد."""
    buffer = io.BytesIO()
    qrcode.make(text).save(buffer, "PNG")
    buffer.seek(0)
    return buffer

def send_proxy_with_qr(proxy_info, latency):
    """یک پست شامل عکس و کپشن اطلاعات پروکسی ارسال می‌کند."""
    caption = (
        f"⚡️ **کانفیگ جدید {proxy_info['protocol']}**\n\n"
        f"🔹 **نام سرور:** `{proxy_info['name']}`\n"
        f"🔹 **پینگ تست:** `{latency}ms`\n\n"
        f"👇 برای کپی، روی کد زیر کلیک کنید:\n"
        f"<code>{proxy_info['config']}</code>\n\n"
        f"📸 یا با دوربین گوشی، کد QR را اسکن کنید."
    )
    qr_image_buffer = generate_qr_code(proxy_info['config'])
    payload = {'chat_id': CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
    files = {'photo': ('v2ray_qr.png', qr_image_buffer, 'image/png')}
    try:
        response = requests.post(TELEGRAM_API_URL, data=payload, files=files, timeout=30)
        response.raise_for_status()
        print(f"Successfully sent V2Ray config: {proxy_info['name']}")
    except Exception as e:
        print(f"Failed to send V2Ray config: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"API Response: {response.text}")

if __name__ == "__main__":
    print("Fetching all V2Ray configs...")
    all_configs = []
    v2ray_protocols = ("vless://", "vmess://", "trojan://", "ss://")
    
    for url in V2RAY_SOURCES:
        try:
            response = requests.get(url, timeout=15)
            # --- بخش اصلاح شده و کلیدی ---
            # ابتدا کل محتوا را دیکود کرده و سپس خط به خط بررسی می‌کنیم
            content = base64.b64decode(response.content).decode('utf-8')
            # فقط خطوطی که با پروتکل‌های معتبر شروع می‌شوند را اضافه می‌کنیم
            all_configs.extend([line.strip() for line in content.strip().split('\n') if line.strip().startswith(v2ray_protocols)])
        except Exception as e:
            print(f"Could not process content from {url}: {e}")

    if not all_configs:
        print("No valid configs found after filtering. Exiting.")
    else:
        # تست یک نمونه تصادفی 50 تایی برای سرعت
        test_sample = random.sample(all_configs, min(len(all_configs), 50))
        print(f"Testing a random sample of {len(test_sample)} configs...")
        
        live_configs_queue = Queue()
        threads = []
        parsed_configs = [parse_config(c) for c in test_sample]

        for config_data in parsed_configs:
            if config_data: # فقط کانفیگ‌هایی که به درستی تجزیه شده‌اند را تست کن
                thread = threading.Thread(target=test_config_latency, args=(config_data, live_configs_queue))
                threads.append(thread)
                thread.start()

        for thread in threads:
            thread.join()

        live_configs_with_latency = list(live_configs_queue.queue)
        
        if not live_configs_with_latency:
            print("No live configs found after testing.")
        else:
            print(f"Found {len(live_configs_with_latency)} live configs.")
            live_configs_with_latency.sort(key=lambda x: x[0])
            best_latency, best_config_info = live_configs_with_latency[0]
            send_proxy_with_qr(best_config_info, best_latency)
