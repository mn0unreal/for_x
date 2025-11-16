import re
import time
import os
import pandas as pd
from pathlib import Path

# selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

# ---------- إعدادات المستخدم ----------
# سيتم البحث تلقائياً عن الملف في المجلد الحالي
# أو ضع المسار الكامل هنا
INPUT_PATH = None  # سيتم البحث تلقائياً، أو ضع المسار مثل: "D:/folder/file.txt"
OUTPUT_PATH = "MOMAH_Accounts_followers.xlsx"
HEADLESS = False  # False للتطوير، True للتشغيل الخفي
DELAY_BETWEEN = 5  # زيادة التأخير لتجنب الحظر
PAGE_LOAD_TIMEOUT = 30  # زيادة وقت التحميل
SCROLL_WAIT = 3  # انتظار بعد التمرير
# ---------------------------------------

def extract_username(url_or_handle: str) -> str:
    """استخراج اسم المستخدم من URL أو handle"""
    s = str(url_or_handle).strip()
    if not s or s.lower() in ["nan", "none", ""]:
        return ""
    
    # إزالة @ في البداية
    if s.startswith("@"):
        return s.lstrip("@")
    
    # استخراج من URL
    # معالجة الشرطة المائلة المزدوجة
    s = re.sub(r'/+', '/', s)
    
    m = re.search(
        r"(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/+([^/?#\s]+)", 
        s, 
        flags=re.IGNORECASE
    )
    if m:
        username = m.group(1)
        # تنظيف اسم المستخدم
        username = username.split('?')[0].split('#')[0]
        return username
    
    # إذا كان نص بسيط
    return s.split("/")[-1].lstrip("@").split('?')[0]

def digits_from_text(txt: str):
    """استخراج الأرقام من النص مع دعم K, M, B"""
    if not txt:
        return None
    
    # إزالة الفواصل العربية والإنجليزية
    txt = txt.replace("،", "").replace("٬", "").replace(",", "").strip()
    
    # البحث عن أنماط مثل 1.2K أو 1.5M
    patterns = [
        r'([\d.]+)\s*[Kk]',  # 1.2K
        r'([\d.]+)\s*[Mm]',  # 1.5M
        r'([\d.]+)\s*[Bb]',  # 1.2B
        r'([\d.]+)\s*ألف',   # عربي
        r'([\d.]+)\s*مليون', # عربي
        r'(\d+)',            # أرقام مباشرة
    ]
    
    for pattern in patterns:
        m = re.search(pattern, txt)
        if m:
            num = float(m.group(1))
            if 'k' in txt.lower() or 'ألف' in txt:
                return int(num * 1_000)
            elif 'm' in txt.lower() or 'مليون' in txt:
                return int(num * 1_000_000)
            elif 'b' in txt.lower():
                return int(num * 1_000_000_000)
            else:
                return int(num)
    
    return None

def setup_driver():
    """إعداد متصفح Chrome"""
    opts = Options()
    
    if HEADLESS:
        opts.add_argument("--headless=new")
    
    # إعدادات لتجنب الكشف
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-setuid-sandbox")
    opts.add_argument("--single-process")
    opts.add_argument("--window-size=1920,1080")
    
    # User agent حقيقي
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    
    # إزالة إشعار "Chrome is being controlled by automated software"
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    
    # إخفاء خاصية webdriver
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    
    return driver

def read_followers_from_profile(driver, profile_url, username):
    """قراءة عدد المتابعين من الملف الشخصي"""
    try:
        driver.get(profile_url)
        time.sleep(SCROLL_WAIT)
        
        # التمرير قليلاً لتحميل المحتوى
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(1)
        
    except TimeoutException:
        print(f"⏱️ Timeout loading: {username}")
        return None, "timeout"
    except Exception as e:
        print(f"❌ Error loading {username}: {str(e)[:50]}")
        return None, f"error: {type(e).__name__}"
    
    # التحقق من وجود الحساب
    try:
        # البحث عن رسائل الخطأ
        page_text = driver.page_source.lower()
        if "this account doesn't exist" in page_text or "هذا الحساب غير موجود" in page_text:
            return None, "account_not_found"
        if "account suspended" in page_text or "تم تعليق الحساب" in page_text:
            return None, "suspended"
        if "these tweets are protected" in page_text or "هذه التغريدات محمية" in page_text:
            return None, "protected"
    except:
        pass
    
    # استراتيجية 1: البحث عن رابط المتابعين
    try:
        # محاولة العثور على عنصر المتابعين
        followers_elements = driver.find_elements(
            By.XPATH, 
            "//a[contains(@href, '/verified_followers') or contains(@href, '/followers')]"
        )
        
        for elem in followers_elements:
            try:
                # البحث في النص
                text = elem.text.strip()
                if text:
                    val = digits_from_text(text)
                    if val is not None:
                        return val, "success"
                
                # البحث في aria-label
                aria = elem.get_attribute("aria-label") or ""
                if aria:
                    val = digits_from_text(aria)
                    if val is not None:
                        return val, "success"
                
                # البحث داخل span
                spans = elem.find_elements(By.TAG_NAME, "span")
                for sp in spans:
                    val = digits_from_text(sp.text.strip())
                    if val is not None:
                        return val, "success"
            except:
                continue
                
    except Exception as e:
        print(f"⚠️ Strategy 1 failed for {username}: {e}")
    
    # استراتيجية 2: البحث في data-testid
    try:
        profile_items = driver.find_elements(
            By.XPATH,
            "//div[contains(@data-testid, 'UserProfileHeader')]//a[contains(@href, '/followers')]"
        )
        
        for item in profile_items:
            val = digits_from_text(item.text)
            if val is not None:
                return val, "success"
    except:
        pass
    
    # استراتيجية 3: البحث في page source
    try:
        source = driver.page_source
        
        # البحث عن أنماط شائعة
        patterns = [
            r'([\d,.]+)\s*Followers',
            r'([\d,.]+)\s*متابع',
            r'"followers_count["\s:]+(\d+)',
            r'followers["\s:]+(\d+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            if matches:
                for match in matches:
                    val = digits_from_text(match)
                    if val is not None and val > 0:
                        return val, "success"
    except:
        pass
    
    return None, "not_found"

def load_accounts(input_path):
    """تحميل الحسابات من ملف Excel أو TXT"""
    
    # إذا لم يتم تحديد مسار، ابحث تلقائياً
    if input_path is None:
        print("🔍 Searching for input files...")
        current_dir = Path.cwd()
        
        # البحث عن ملفات محتملة
        search_patterns = [
            "*account*.txt",
            "*account*.xlsx", 
            "MOMAH*.txt",
            "MOMAH*.xlsx",
            "*.txt",
            "*.xlsx"
        ]
        
        found_files = []
        for pattern in search_patterns:
            found_files.extend(current_dir.glob(pattern))
            if found_files:
                break
        
        if not found_files:
            print(f"\n❌ No input files found in: {current_dir}")
            print("\nPlease provide one of:")
            print("  • Excel file (.xlsx) with account URLs/usernames")
            print("  • Text file (.txt) with one URL per line")
            print("\nOr set INPUT_PATH in the script to the full file path")
            raise FileNotFoundError("No input file found")
        
        # استخدام أول ملف تم العثور عليه
        input_path = found_files[0]
        print(f"✅ Found file: {input_path.name}")
    
    path = Path(input_path)
    
    if not path.exists():
        print(f"\n❌ File not found: {input_path}")
        print(f"Current directory: {Path.cwd()}")
        print("\nFiles in current directory:")
        for f in Path.cwd().iterdir():
            if f.is_file():
                print(f"  • {f.name}")
        raise FileNotFoundError(f"File not found: {input_path}")
    
    if path.suffix.lower() == '.xlsx':
        df = pd.read_excel(input_path)
        # البحث عن العمود المناسب
        candidate_cols = [
            c for c in df.columns 
            if any(k in str(c).lower() for k in ("url", "handle", "account", "username", "link"))
        ]
        col = candidate_cols[0] if candidate_cols else df.columns[0]
        print(f"📊 Using column: {col}")
        accounts = df[col].astype(str).fillna("").tolist()
        
    elif path.suffix.lower() == '.txt':
        with open(input_path, 'r', encoding='utf-8') as f:
            accounts = [line.strip() for line in f if line.strip()]
        print(f"📄 Loaded {len(accounts)} accounts from TXT file")
    
    else:
        raise ValueError(f"❌ Unsupported file format: {path.suffix}")
    
    # إزالة التكرارات مع الحفاظ على الترتيب
    seen = set()
    unique_accounts = []
    duplicates = []
    
    for acc in accounts:
        username = extract_username(acc)
        if username and username.lower() not in seen:
            seen.add(username.lower())
            unique_accounts.append(acc)
        elif username:
            duplicates.append(acc)
    
    if duplicates:
        print(f"⚠️ Found {len(duplicates)} duplicate accounts (removed)")
    
    return unique_accounts

def main():
    print("=" * 60)
    print("🚀 Twitter Follower Counter - MOMAH Edition")
    print("=" * 60)
    
    try:
        accounts = load_accounts(INPUT_PATH)
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return
    
    print(f"📋 Total accounts to process: {len(accounts)}")
    print(f"⏱️ Estimated time: ~{len(accounts) * DELAY_BETWEEN / 60:.1f} minutes")
    print("\n" + "=" * 60)
    
    driver = setup_driver()
    results = []
    session_error_count = 0
    
    try:
        for i, acc in enumerate(tqdm(accounts, desc="🔍 Processing"), 1):
            username = extract_username(acc)
            
            if not username:
                results.append({
                    "input": acc,
                    "username": "",
                    "profile_url": "",
                    "followers": None,
                    "status": "invalid_input"
                })
                continue
            
            profile_url = f"https://x.com/{username}"
            
            try:
                followers, status = read_followers_from_profile(driver, profile_url, username)
                session_error_count = 0  # Reset on success
                
                results.append({
                    "input": acc,
                    "username": username,
                    "profile_url": profile_url,
                    "followers": followers,
                    "status": status
                })
                
                # طباعة النتيجة
                if followers is not None:
                    print(f"\n✅ {username}: {followers:,} followers")
                else:
                    print(f"\n⚠️ {username}: {status}")
                    
            except Exception as e:
                error_name = type(e).__name__
                print(f"\n❌ Error loading {username}: {str(e)[:100]}")
                
                # Handle session errors by restarting driver
                if "InvalidSessionId" in error_name or "session" in str(e).lower():
                    session_error_count += 1
                    if session_error_count <= 3:
                        print("🔄 Restarting browser session...")
                        try:
                            driver.quit()
                        except:
                            pass
                        time.sleep(2)
                        driver = setup_driver()
                        print("✅ Browser restarted, retrying current account...")
                        # Retry the current account
                        try:
                            followers, status = read_followers_from_profile(driver, profile_url, username)
                            session_error_count = 0
                            results.append({
                                "input": acc,
                                "username": username,
                                "profile_url": profile_url,
                                "followers": followers,
                                "status": status
                            })
                            if followers is not None:
                                print(f"\n✅ {username}: {followers:,} followers")
                            else:
                                print(f"\n⚠️ {username}: {status}")
                            continue
                        except Exception as retry_e:
                            print(f"❌ Retry failed: {str(retry_e)[:50]}")
                    else:
                        print("❌ Too many session errors, stopping...")
                        break
                
                results.append({
                    "input": acc,
                    "username": username,
                    "profile_url": profile_url,
                    "followers": None,
                    "status": f"error: {error_name}"
                })
            
            # تأخير بين الطلبات
            if i < len(accounts):
                time.sleep(DELAY_BETWEEN)
                
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
    finally:
        driver.quit()
        print("\n🔒 Browser closed")
    
    # حفظ النتائج
    out_df = pd.DataFrame(results)
    out_df.to_excel(OUTPUT_PATH, index=False)
    
    # إحصائيات
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total processed: {len(results)}")
    print(f"Successful: {sum(1 for r in results if r['followers'] is not None)}")
    print(f"Failed: {sum(1 for r in results if r['followers'] is None)}")
    print(f"\n💾 Results saved to: {OUTPUT_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()