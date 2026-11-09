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

# 假期查询计划
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
    print("开始云端查票（暴力直查版，无视残缺白名单）...")
    cookie_str = asyncio.run(get_auto_cookie())
    if not cookie_str: return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Referer": "https://ecactivity.ceair.com/qysz-coupon/home.html",
        "Origin": "https://ecactivity.ceair.com"
    }

    # 拆分上海虹桥(SHA)和上海浦东(PVG)
    my_origins = {
        "上海虹桥": "SHA", "上海浦东": "PVG", 
        "无锡": "WUX", "南京": "NKG", "杭州": "HGH", "嘉兴": "JXS", "南通": "NTG", "常州": "CZX"
    }
    
    # 目标目的地
    my_targets = {
        "乌鲁木齐": "URC", "喀什": "KHG", "伊宁": "YIN", "库尔勒": "KRL", "阿克苏": "AKU", 
        "阿勒泰": "AAT", "库车": "KCA", "博乐": "BPL", "塔城": "TCG", "哈密": "HMI", 
        "昭苏": "ZFL", "富蕴": "FYN", "布尔津": "KJI", "吐鲁番": "TLQ", "若羌": "RQA",
        "拉萨": "LXA", "日喀则": "RKZ", "林芝": "LZY", "昌都": "BPX", "阿里": "NGQ",
        "西双版纳": "JHG", "北京": "BJS"
    }

    # 直接生成所有的排列组合，不再经过白名单
    go_routes, back_routes = [], []
    for o_name, o_code in my_origins.items():
        for t_name, t_code in my_targets.items():
            go_routes.append((o_name, o_code, t_name, t_code))
            back_routes.append((t_name, t_code, o_name, o_code))

    api_detail = "https://ecskgateway.ceair.com/openApi/redeemable/queryRedeemableDetailNew"
    all_results = []
    request_count = 0

    # 1. 常规查票循环
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

    # 2. 秋假去程成都专线
    autumn_config = next((c for c in TRIP_CONFIGS if c["name"] == "秋假"), None)
    if autumn_config:
        print("\n开始查询秋假特殊航线：华东 -> 成都 (去程)")
        chengdu_start = datetime.strptime(autumn_config["go_start"], "%Y-%m-%d")
        chengdu_end = datetime.strptime(autumn_config["go_end"], "%Y-%m-%d")
        
        chengdu_routes = []
        for o_name, o_code in my_origins.items():
            chengdu_routes.append((o_name, o_code, "成都", "CTU"))
                
        for dep_name, dep_code, arr_name, arr_code in chengdu_routes:
            current_date = chengdu_start
            while current_date <= chengdu_end:
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
                            if chengdu_start <= check_date_obj <= chengdu_end and status == "2":
                                all_results.append({
                                    "假期": "秋假", "出发地": dep_name, "目的地": arr_name,
                                    "日期": check_dt, "行程": "去程"
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

    print(f"\n查票完成，共发现 {len(all_results)} 个有票行程。")
    send_bark_push(all_results)

if __name__ == "__main__":
    main()
