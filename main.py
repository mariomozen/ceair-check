import requests
import time
import sys
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

BARK_KEY = os.environ.get('BARK_KEY', '')

# 只保留秋假和春节
TRIP_CONFIGS = [
    {"name": "秋假", "go_start": "2026-11-13", "go_end": "2026-11-14", "back_start": "2026-11-17", "back_end": "2026-11-18"},
    {"name": "春节", "go_start": "2027-02-07", "go_end": "2027-02-08", "back_start": "2027-02-13", "back_end": "2027-02-14"}
]

def send_bark_push(all_results):
    if not BARK_KEY or not all_results:
        return
    
    grouped = {}
    for item in all_results:
        trip = item['假期']
        if trip not in grouped: grouped[trip] = []
        grouped[trip].append(item)

    content_lines = ["✈️ 发现新票！", ""]
    for trip, items in grouped.items():
        content_lines.append(f"【{trip}】")
        for i in items:
            content_lines.append(f"{i['出发地']}➔{i['目的地']} {i['日期']} ({i['行程']})")
        content_lines.append("")
    
    content = "\n".join(content_lines)
    
    try:
        requests.get(f"https://api.day.app/{BARK_KEY}/东航趣游卡有新票/{content}", timeout=10)
        print("✅ Bark 推送发送成功！")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

async def get_auto_cookie():
    print("正在启动云端浏览器获取最新动态 Cookie...")
    cookies_list = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        try:
            await page.goto("https://ecactivity.ceair.com/qysz-coupon/home.html", timeout=30000)
            await page.wait_for_timeout(5000)
            cookies = await context.cookies()
            for c in cookies:
                cookies_list.append(f"{c['name']}={c['value']}")
            print("✅ 成功获取动态 Cookie！")
        except Exception as e:
            print(f"❌ 获取 Cookie 失败: {e}")
        finally:
            await browser.close()
    return "; ".join(cookies_list)

def main():
    print("开始云端查票...")
    cookie_str = asyncio.run(get_auto_cookie())
    if not cookie_str: return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Referer": "https://ecactivity.ceair.com/qysz-coupon/home.html",
        "Origin": "https://ecactivity.ceair.com"
    }

    # 获取白名单
    api_url = "https://ecskgateway.ceair.com/openApi/redeemable/queryRedeemableRouteListV2"
    payload = {"channelCode": "NzcwMQ==", "flightType": "D", "productCode": "YRDCCN0525", "salesChannel": "NzcwMQ=="}
    valid_routes = set()
    try:
        res = requests.post(api_url, headers=headers, json=payload, timeout=15)
        if res.json().get("success"):
            for item in res.json().get("data", {}).get("redeemableRouteList", []):
                if item.get("oriCityCode") and item.get("desCityCode"):
                    valid_routes.add((item.get("oriCityCode"), item.get("desCityCode")))
    except Exception as e:
        print(f"获取白名单失败: {e}")
        return

    my_origins = {"上海": "SHA", "无锡": "WUX", "南京": "NKG", "杭州": "HGH", "嘉兴": "JXS", "南通": "NTG", "常州": "CZX"}
    my_targets = {
        "乌鲁木齐": "URC", "喀什": "KHG", "伊宁": "YIN", "库尔勒": "KRL", "阿克苏": "AKU", 
        "阿勒泰": "AAT", "库车": "KCA", "博乐": "BPL", "塔城": "TCG", "哈密": "HMI", 
        "昭苏": "ZFL", "富蕴": "FYN", "布尔津": "KJI", "吐鲁番": "TLQ", "若羌": "RQA",
        "拉萨": "LXA", "日喀则": "RKZ", "林芝": "LZY", "昌都": "BPX", "阿里": "NGQ"
    }

    go_routes, back_routes = [], []
    for o_name, o_code in my_origins.items():
        for t_name, t_code in my_targets.items():
            if (o_code, t_code) in valid_routes: go_routes.append((o_name, o_code, t_name, t_code))
            if (t_code, o_code) in valid_routes: back_routes.append((t_name, t_code, o_name, o_code))

    api_detail = "https://ecskgateway.ceair.com/openApi/redeemable/queryRedeemableDetailNew"
    all_results = []
    request_count = 0

    # 常规查票循环
    for config in TRIP_CONFIGS:
        trip_name = config["name"]
        tasks = [
            ("去程", go_routes, datetime.strptime(config["go_start"], "%Y-%m-%d"), datetime.strptime(config["go_end"], "%Y-%m-%d")),
            ("返程", back_routes, datetime.strptime(config["back_start"], "%Y-%m-%d"), datetime.strptime(config["back_end"], "%Y-%m-%d"))
        ]
        
        for trip_type, routes, start_dt, end_dt in tasks:
            for route in routes:
                dep_name, dep_code, arr_name, arr_code = route
                current_date = start_dt
                while current_date <= end_dt:
                    date_str = current_date.strftime("%Y-%m-%d")
                    payload = {
                        "channelCode": "NzcwMQ==", "depDate": date_str, "desCityCode": arr_code,
                        "indexNo": "1", "oriCityCode": dep_code, "productCode": "YRDCCN0525",
                        "routeType": "OW", "salesChannel": "NzcwMQ=="
                    }
                    try:
                        res = requests.post(api_detail, headers=headers, json=payload, timeout=15)
                        r_data = res.json()
                        if r_data.get("success"):
                            d_map = (r_data.get("data") or {}).get("redeemableDetailMap") or {}
                            for check_dt, status in d_map.items():
                                check_date_obj = datetime.strptime(check_dt, "%Y-%m-%d")
                                if start_dt <= check_date_obj <= end_dt and status == "2":
                                    all_results.append({
                                        "假期": trip_name, "出发地": dep_name, "目的地": arr_name,
                                        "日期": check_dt, "行程": trip_type
                                    })
                    except Exception:
                        pass
                    
                    request_count += 1
                    if request_count % 10 == 0:
                        print("防封休息 5 秒...")
                        time.sleep(5.0)
                    else:
                        time.sleep(random.uniform(1.5, 3.0))
                    current_date += timedelta(days=7)

    # ==========================================
    # 🌟 新增：精准特殊单程查询（11.13 上海/无锡 -> 北京）
    # ==========================================
    print("\n开始查询特殊单程：2026-11-13 上海/无锡 -> 北京")
    special_routes = [
        ("上海", "SHA", "北京", "BJS"),
        ("无锡", "WUX", "北京", "BJS")
    ]
    for dep_name, dep_code, arr_name, arr_code in special_routes:
        date_str = "2026-11-13"
        payload = {
            "channelCode": "NzcwMQ==", "depDate": date_str, "desCityCode": arr_code,
            "indexNo": "1", "oriCityCode": dep_code, "productCode": "YRDCCN0525",
            "routeType": "OW", "salesChannel": "NzcwMQ=="
        }
        try:
            res = requests.post(api_detail, headers=headers, json=payload, timeout=15)
            r_data = res.json()
            if r_data.get("success"):
                d_map = (r_data.get("data") or {}).get("redeemableDetailMap") or {}
                for check_dt, status in d_map.items():
                    if check_dt == "2026-11-13" and status == "2":
                        all_results.append({
                            "假期": "北京单程",
                            "出发地": dep_name,
                            "目的地": arr_name,
                            "日期": check_dt,
                            "行程": "去程"
                        })
        except Exception:
            pass
        time.sleep(random.uniform(1.5, 3.0))

    print(f"查票完成，共发现 {len(all_results)} 个有票行程。")
    send_bark_push(all_results)

if __name__ == "__main__":
    main()
