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


def get_menu_image() -> bytes:
    """카카오 채널 최신 게시글 이미지 URL을 찾아 다운로드한다"""
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
        driver.get(KAKAO_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "img"))
        )

        # 스크롤을 내려 게시글 이미지 로딩
        for _ in range(8):
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(0.8)
        time.sleep(2)

        # 모든 img src 출력 (디버그)
        imgs = driver.find_elements(By.TAG_NAME, "img")
        print(f"   [디버그] img 총 {len(imgs)}개")
        for i, img in enumerate(imgs):
            src = img.get_attribute("src") or ""
            w = img.size.get("width", 0)
            h = img.size.get("height", 0)
            print(f"   [디버그] [{i}] {w}x{h} {src[:100]}")

        # kakaocdn 이미지 중 가장 큰 것 선택
        best_url = None
        max_area = 0
        for img in imgs:
            src = img.get_attribute("src") or ""
            if "kakaocdn" not in src and "kakao.co.kr" not in src:
                continue
            w = img.size.get("width", 0)
            h = img.size.get("height", 0)
            if w * h > max_area and w > 100 and h > 100:
                max_area = w * h
                best_url = src

        if best_url:
            print(f"   [디버그] 선택된 이미지 URL: {best_url[:100]}")
            # 이미지 직접 다운로드
            res = requests.get(best_url, timeout=15)
            res.raise_for_status()
            img_bytes = res.content
        else:
            # 못 찾으면 전체 스크린샷
            print("   게시글 이미지를 못 찾아 전체 스크린샷 사용")
            img_bytes = driver.get_screenshot_as_png()

        # 이미지 압축 (Gemini 업로드 크기 제한 대응)
        img_obj = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_obj.thumbnail((1200, 1200))  # 최대 1200px로 축소
        buf = io.BytesIO()
        img_obj.save(buf, format="JPEG", quality=85)
        compressed = buf.getvalue()
        print(f"   이미지 크기: {len(img_bytes):,} → {len(compressed):,} bytes")
        return compressed

    finally:
        driver.quit()


def extract_menu(image_bytes: bytes) -> str:
    """Gemini API로 메뉴 텍스트 추출"""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
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
    res = requests.post(url, json=payload, timeout=30)
    print(f"   [디버그] Gemini 응답코드: {res.status_code}")
    if res.status_code != 200:
        print(f"   [디버그] Gemini 응답내용: {res.text[:300]}")
    res.raise_for_status()
    return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def send_to_teams(menu_text: str):
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
    res = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=15)
    res.raise_for_status()
    print("Teams 전송 완료!")


def main():
    print("1) 카카오 채널 이미지 가져오는 중...")
    img = get_menu_image()
    print(f"   완료 ({len(img):,} bytes)")

    print("2) Gemini로 메뉴 분석 중...")
    menu = extract_menu(img)
    print("   추출된 메뉴:\n", menu)

    print("3) Teams로 전송 중...")
    send_to_teams(menu)
    print("완료!")


if __name__ == "__main__":
    main()
