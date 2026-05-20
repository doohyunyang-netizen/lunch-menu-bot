import os
import time
import base64
import requests
import re
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
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
KAKAO_URL         = "https://pf.kakao.com/_yxgQDb/posts"


def get_today_image() -> bytes | None:
    today = date.today()
    today_pattern = f"{str(today.year)[2:]}/{today.month}/{today.day}"
    print(f"   오늘 날짜 패턴: {today_pattern}")

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
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        for _ in range(10):
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(0.5)
        time.sleep(3)

        body_text = driver.find_element(By.TAG_NAME, "body").text
        if today_pattern not in body_text:
            print(f"   오늘({today_pattern}) 게시글이 아직 없어요.")
            return None
        print("   오늘 게시글 확인!")

        source = driver.page_source
        urls = list(dict.fromkeys(
            re.findall(r'https://k\.kakaocdn\.net/dn/[^"\']+/img_xl\.jpg', source)
        ))
        print(f"   img_xl URL {len(urls)}개 발견")

        if not urls:
            print("   이미지 URL을 찾지 못했어요.")
            return None

        img_url = urls[0]
        print(f"   선택: {img_url}")
        res = requests.get(img_url, timeout=15)
        res.raise_for_status()

        img_obj = Image.open(io.BytesIO(res.content)).convert("RGB")
        img_obj.thumbnail((1200, 1200))
        buf = io.BytesIO()
        img_obj.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    finally:
        driver.quit()


def extract_menu(image_bytes: bytes) -> str:
    """Gemini API로 이미지에서 메뉴 추출 (모델 순차 시도)"""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    text_prompt = (
        "이 이미지는 오늘의 구내식당 메뉴판입니다. "
        "이미지에 보이는 메뉴를 아래 형식으로 보기 좋게 정리해 주세요.\n\n"
        "형식 예시:\n"
        "🍜 국/찌개: 감자탕\n"
        "🍗 메인: 순살닭다리살양념볶음, 통살후르츠탕수육\n"
        "🥘 사이드: 해물부추전, 미니찐빵찜\n"
        "🥗 샐러드: 양배추샐러드\n"
        "🥒 김치/반찬: 수제깍두기, 콩나물무침, 배추김치\n"
        "🍰 후식: 필라델피아크림치즈, 누텔라쵸코, 제철과일\n"
        "☕ 음료: 매실차, 보리차, 믹스커피\n\n"
        "이미지에 없는 항목은 생략하고, "
        "각 줄 앞에 어울리는 이모지를 붙여 주세요. "
        "메뉴 정보가 전혀 보이지 않으면 "
        "'메뉴 이미지를 확인할 수 없습니다.'라고만 답해 주세요."
    )

    # 한도 초과시 자동으로 다음 모델로
    MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
    ]

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": text_prompt}
            ]
        }]
    }

    for model in MODELS:
        print(f"   모델 시도: {model}")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        res = requests.post(url, json=payload, timeout=30)
        print(f"   응답코드: {res.status_code}")
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"   실패: {res.text[:200]}")

    raise Exception("모든 Gemini 모델 시도 실패")


def send_to_teams(menu_text: str):
    today = date.today().strftime("%Y년 %m월 %d일")
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"{today} 점심 메뉴",
        "themeColor": "2BAE66",
        "title": f"🍽️ {today} 점심 메뉴",
        "text": menu_text.replace("\n", "<br>"),
    }
    res = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=15)
    res.raise_for_status()
    print("Teams 채널 전송 완료!")


def send_to_slack(menu_text: str):
    today = date.today().strftime("%Y년 %m월 %d일")
    payload = {
        "text": f"🍽️ *{today} 점심 메뉴*\n{menu_text}"
    }
    res = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=15)
    res.raise_for_status()
    print("Slack 전송 완료!")


def main():
    print("1) 오늘 게시글 이미지 가져오는 중...")
    img = get_today_image()

    if img is None:
        print("   오늘 게시글이 없어 종료합니다.")
        return

    print(f"   완료 ({len(img):,} bytes)")

    print("2) Gemini로 메뉴 분석 중...")
    menu = extract_menu(img)
    print("   추출된 메뉴:\n", menu)

    print("3) Teams 채널로 전송 중...")
    send_to_teams(menu)

    print("4) Slack으로 전송 중...")
    send_to_slack(menu)
    print("완료!")


if __name__ == "__main__":
    main()
