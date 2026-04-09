import os
import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
import io
from datetime import date

GEMINI_API_KEY    = os.environ["GEMINI_API_KEY"]
TEAMS_WEBHOOK_URL = os.environ["TEAMS_WEBHOOK_URL"]
KAKAO_URL         = "https://pf.kakao.com/_yxgQDb/posts"


def capture_page_image(url: str) -> bytes:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,1800")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "img"))
        )
        time.sleep(4)

        # ── 디버그: 페이지 제목과 URL 출력 ──
        print(f"   [디버그] 페이지 제목: {driver.title}")
        print(f"   [디버그] 현재 URL: {driver.current_url}")

        # ── 디버그: 전체 스크린샷을 파일로 저장 ──
        driver.save_screenshot("debug_screenshot.png")
        print("   [디버그] debug_screenshot.png 저장 완료")

        # ── 디버그: 발견된 img 태그 목록 출력 ──
        imgs = driver.find_elements(By.TAG_NAME, "img")
        print(f"   [디버그] img 태그 총 {len(imgs)}개 발견")
        for i, img in enumerate(imgs[:10]):
            src = img.get_attribute("src") or ""
            w = img.size.get("width", 0)
            h = img.size.get("height", 0)
            print(f"   [디버그] img[{i}] {w}x{h} | {src[:80]}")

        target = None
        for img in imgs:
            src = img.get_attribute("src") or ""
            if "kakaocdn" in src or "kakao.co.kr" in src:
                w = img.size.get("width", 0)
                h = img.size.get("height", 0)
                if w > 100 and h > 100:
                    target = img
                    break

        png = driver.get_screenshot_as_png()

        if target:
            loc  = target.location
            size = target.size
            print(f"   [디버그] 타겟 이미지 위치: {loc}, 크기: {size}")
            img_obj = Image.open(io.BytesIO(png))
            left   = int(loc["x"])
            top    = int(loc["y"])
            right  = int(loc["x"] + size["width"])
            bottom = int(loc["y"] + size["height"])
            if right > left and bottom > top:
                cropped = img_obj.crop((left, top, right, bottom))
                buf = io.BytesIO()
                cropped.save(buf, format="PNG")
                return buf.getvalue()

        print("   특정 이미지를 찾지 못해 전체 스크린샷을 사용합니다.")
        return png
    finally:
        driver.quit()


def extract_menu(image_bytes: bytes) -> str:
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png", "data": b64}},
                {"text": (
                    "이 이미지는 오늘의 구내식당 메뉴판입니다. "
                    "이미지에 보이는 메뉴를 아래 형식으로 요약해 주세요.\n\n"
                    "형식:\n"
                    "• [코너 또는 구분]: 메뉴1, 메뉴2, ...\n\n"
                    "메뉴 정보가 전혀 보이지 않으면 "
                    "'메뉴 이미지를 확인할 수 없습니다.'라고만 답해 주세요."
                )}
            ]
        }]
    }

    for attempt in range(5):
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"   429 한도 초과, {wait}초 후 재시도... ({attempt+1}/5)")
            time.sleep(wait)
            continue
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    raise Exception("Gemini API 429 오류: 5회 재시도 후에도 실패했습니다.")


def send_to_teams(webhook_url: str, menu_text: str):
    today = date.today().strftime("%Y년 %m월 %d일")
    body  = menu_text.replace("\n", "<br>")
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"{today} 점심 메뉴",
        "themeColor": "2BAE66",
        "title": f"🍽️ {today} 점심 메뉴",
        "text": body,
    }
    res = requests.post(webhook_url, json=payload, timeout=15)
    res.raise_for_status()
    print("Teams 전송 완료!")


def main():
    print("1) 카카오 채널 페이지 열어 이미지 캡처 중...")
    img = capture_page_image(KAKAO_URL)
    print(f"   캡처 완료 ({len(img):,} bytes)")

    print("2) Gemini로 메뉴 분석 중...")
    menu = extract_menu(img)
    print("   추출된 메뉴:\n", menu)

    print("3) Teams로 전송 중...")
    send_to_teams(TEAMS_WEBHOOK_URL, menu)
    print("완료!")


if __name__ == "__main__":
    main()
