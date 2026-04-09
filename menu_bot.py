import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TEAMS_WEBHOOK_URL = os.environ["TEAMS_WEBHOOK_URL"]
KAKAO_URL         = "https://pf.kakao.com/_yxgQDb/posts"


def debug_page():
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

        # 페이지 전체 텍스트 출력 (날짜 형식 확인용)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print("=== 페이지 전체 텍스트 ===")
        print(body_text[:5000])
        print("=== 끝 ===")

        # 페이지 소스에서 날짜 관련 키워드 찾기
        source = driver.page_source
        import re
        # 날짜 패턴 찾기 (예: 2026, 26.4, 4월 등)
        dates = re.findall(r'202[0-9][./년-]\d{1,2}[./월-]\d{1,2}|26\.\d{1,2}\.\d{1,2}|\d{4}년 \d{1,2}월 \d{1,2}일', source)
        print(f"\n=== 날짜 패턴 {len(dates)}개 ===")
        for d in dates[:20]:
            print(d)

    finally:
        driver.quit()


def main():
    print("페이지 구조 분석 중...")
    debug_page()


if __name__ == "__main__":
    main()
