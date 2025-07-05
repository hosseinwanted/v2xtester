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
from urllib.parse import unquote, urlparse, quote

# --- تنظیمات اصلی ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
V2RAY_SOURCES = [
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vmess.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vless.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/trojan.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/ss.txt"
]
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

# !!! این بخش را با یوزرنیم کانال خود پر کنید !!!
MAIN_CHANNEL_USERNAME = "@YourV2rayChannel"

def parse_config(config_str):
    """نام، پروتکل، آدرس و شناسه را از کانفیگ استخراج می‌کند."""
    try:
        protocol = config_str.split("://")[0]
        base_config = config_str.split("#")[0]
        
        original_name = ""
        config_id = ""
        if "#" in config_str:
            original_name = unquote(config_str.split("#")[-1]).strip()
            # استخراج شناسه عددی از انتهای نام
            if "|" in original_name:
                config_id = original_name.split("|")[-1].strip()

        address = ""
        if protocol == "vmess":
            try:
                vmess_json_str = base64.b64decode(base_config.split("://")[1]).decode('utf-8')
                address = json.loads(vmess_json_str).get("add", "")
            except Exception: pass
        if not address:
            parsed_url = urlparse(base_config)
            address = parsed_url.hostname
            if not address and "@" in parsed_url.path:
                address = parsed_url.path.split("@")[1].split(":")[0]
        
        return {"protocol": protocol.upper(), "address": address, "base_config": base_config, "id": config_id}
    except Exception as e:
        print(f"Error parsing config: {e}")
        return None

def create_new_config(base_config, channel_username, config_id):
    """یک کانفیگ جدید با نام اختصاصی شامل شناسه می‌سازد."""
    new_name = f"🚀 {channel_username} | ID-{config_id}"
    encoded_name = quote(new_name)
    return f"{base_config}#{encoded_name}"

def test_config_latency(config_info, result_queue, timeout=2.5):
    """سلامت سرور را تست می‌کند."""
    if not config_info or not config_info.get("address"): return
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
    """یک تصویر کد QR سفارشی و کوچک‌تر تولید می‌کند."""
    buffer = io.BytesIO()
    qrcode.make(text, box_size=6, border=2).save(buffer, "PNG")
    buffer.seek(0)
    return buffer

def send_proxy_with_qr(final_config_str, latency):
    """یک پست شامل عکس و کپشن با نام جدید ارسال می‌کند."""
    protocol = final_config_str.split("://")[0].upper()
    display_name = unquote(final_config_str.split("#")[-1])
    caption = (
        f"⚡️ <b>کانفیگ جدید {protocol}</b>\n\n"
        f"🔹 <b>نام سرور:</b> <code>{display_name}</code>\n"
        f"🔹 <b>پینگ تست:</b> <code>{latency}ms</code>\n\n"
        f"👇 برای کپی، روی کد زیر کلیک کنید:\n"
        f"<code>{final_config_str}</code>\n\n"
        f"📸 یا با دوربین گوشی، کد QR را اسکن کنید.\n\n"
        f"#V2Ray #{protocol}"
    )
    qr_image_buffer = generate_qr_code(final_config_str)
    payload = {'chat_id': CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
    files = {'photo': ('v2ray_qr.png', qr_image_buffer, 'image/png')}
    
    try:
        response = requests.post(TELEGRAM_API_URL, data=payload, files=files, timeout=30)
        response.raise_for_status()
        print(f"Successfully sent new V2Ray config: {display_name}")
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
            content = base64.b64decode(response.content).decode('utf-8')
            all_configs.extend([line.strip() for line in content.strip().split('\n') if line.strip().startswith(v2ray_protocols)])
        except Exception as e:
            print(f"Could not process content from {url}: {e}")

    if not all_configs:
        print("No valid configs found after filtering. Exiting.")
    else:
        test_sample = random.sample(all_configs, min(len(all_configs), 50))
        print(f"Testing a random sample of {len(test_sample)} configs...")
        
        live_configs_queue = Queue()
        threads = []
        parsed_configs = [parse_config(c) for c in test_sample]

        for config_data in parsed_configs:
            if config_data:
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
            
            # --- بخش اصلاح شده: استفاده از شناسه برای ساخت نام ---
            final_config = create_new_config(
                best_config_info['base_config'], 
                MAIN_CHANNEL_USERNAME, 
                best_config_info['id']
            )
            
            send_proxy_with_qr(final_config, best_latency)
