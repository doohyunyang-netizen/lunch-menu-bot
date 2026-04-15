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

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TEAMS_WEBHOOK_URL  = os.environ["TEAMS_WEBHOOK_URL"]
SLACK_WEBHOOK_URL  = os.environ["SLACK_WEBHOOK_URL"]
KAKAO_URL          = "https://pf.kakao.com/_yxgQDb/posts"


def get_today_image() -> bytes | None:
    """오늘 날짜 게시글 이미지만 가져온다"""
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
        print(f"   오늘 게시글 확인!")

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
    """OpenRouter API로 이미지에서 메뉴 텍스트 추출"""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "이 이미지는 오늘의 구내식당 메뉴판입니다. "
                        "이미지에 보이는 메뉴를 아래 형식으로 요약해 주세요.\n\n"
                        "형식:\n"
                        "• [구분]: 메뉴1, 메뉴2, ...\n\n"
                        "메뉴 정보가 전혀 보이지 않으면 "
                        "'메뉴 이미지를 확인할 수 없습니다.'라고만 답해 주세요."
                    )
                },
            ],
        }],
    }

    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers, json=payload, timeout=30
    )
    print(f"   OpenRouter 응답코드: {res.status_code}")
    if res.status_code != 200:
        print(f"   OpenRouter 오류: {res.text[:300]}")
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"].strip()


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
    print("Teams 전송 완료!")


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

    print("2) OpenRouter로 메뉴 분석 중...")
    menu = extract_menu(img)
    print("   추출된 메뉴:\n", menu)

    print("3) Teams로 전송 중...")
    send_to_teams(menu)

    print("4) Slack으로 전송 중...")
    send_to_slack(menu)
    print("완료!")


if __name__ == "__main__":
    main()
