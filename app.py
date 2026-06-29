import os
import json
import glob
import hmac
import hashlib
import re
from datetime import datetime, date, timedelta
from urllib.parse import urlencode
from io import BytesIO

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.credentials import Credentials as GoogleCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    GOOGLE_DRIVE_LIBS_AVAILABLE = True
except Exception:
    GoogleAuthRequest = None
    GoogleCredentials = None
    InstalledAppFlow = None
    google_build = None
    MediaIoBaseDownload = None
    MediaIoBaseUpload = None
    GOOGLE_DRIVE_LIBS_AVAILABLE = False

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# Karl's Health Dashboard
# ============================================================

st.set_page_config(
    page_title="Karl's Health Dashboard",
    page_icon="💙",
    layout="wide",
)


# ============================================================
# Basic settings
# ============================================================

APP_TITLE = "Karl's Health Dashboard"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TOKEN_FILE = os.path.join(BASE_DIR, "withings_tokens.json")
GOOGLE_CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "google_client_secret.json")
GOOGLE_DRIVE_TOKEN_FILE = os.path.join(BASE_DIR, "google_drive_token.json")
GOOGLE_DRIVE_WITHINGS_FILENAME = "karls_health_dashboard_withings_tokens.json"
GOOGLE_DRIVE_FOOD_PREFIX = "karls_health_dashboard_food__"
GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
GOALS_FILE = os.path.join(BASE_DIR, "dashboard_goals.json")
MEDICATIONS_FILE = os.path.join(BASE_DIR, "medications.csv")
APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.csv")
HEALTH_NOTES_FILE = os.path.join(BASE_DIR, "health_notes.csv")

GOOGLE_DRIVE_GOALS_FILENAME = "karls_health_dashboard_dashboard_goals.json"
GOOGLE_DRIVE_MEDICATIONS_FILENAME = "karls_health_dashboard_medications.csv"
GOOGLE_DRIVE_APPOINTMENTS_FILENAME = "karls_health_dashboard_appointments.csv"
GOOGLE_DRIVE_HEALTH_NOTES_FILENAME = "karls_health_dashboard_health_notes.csv"

ENV_FILE = os.path.join(BASE_DIR, ".env")

WITHINGS_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
WITHINGS_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
WITHINGS_SCOPE = "user.info,user.metrics,user.activity"

HEALTH_NOTE_COLUMNS = [
    "Date",
    "Pain 0-10",
    "Brain fog 0-10",
    "Fatigue 0-10",
    "Mood",
    "Sleep quality",
    "Symptoms / Notes",
    "Questions for clinician",
]

DEFAULT_GOALS = {
    "sleep_hours": 7.0,
    "steps": 7000,
    "calories": 1800,
    "protein_g": 135,
    "carbs_pct": 40,
    "protein_pct": 30,
    "fat_pct": 30,
    "fluids_l": 2.0,
    "target_weight_stones": 15.0,
}

DEFAULT_MEDICATIONS = [
    {"Medication": "Adcal-D3", "Dose": "1 chewable tablet", "When": "Twice daily", "What it is for": "Calcium and vitamin D support", "Notes": ""},
    {"Medication": "Carvedilol", "Dose": "6.25mg", "When": "Twice daily", "What it is for": "Portal hypertension / blood pressure support", "Notes": ""},
    {"Medication": "Centrum Advance 50+", "Dose": "1 tablet", "When": "Once daily", "What it is for": "Multivitamin support", "Notes": ""},
    {"Medication": "Creon 25,000", "Dose": "As prescribed", "When": "With meals and snacks", "What it is for": "Pancreatic enzyme support / digestion", "Notes": "Take with food."},
    {"Medication": "Duloxetine", "Dose": "As prescribed", "When": "Once daily", "What it is for": "Mood and chronic pain support", "Notes": ""},
    {"Medication": "Forceval", "Dose": "1 capsule", "When": "Once daily, 1 hour after food", "What it is for": "Vitamin and nutritional support", "Notes": ""},
    {"Medication": "Lactulose", "Dose": "20ml", "When": "Up to 4 times daily", "What it is for": "Hepatic encephalopathy support", "Notes": "Dose may vary depending on symptoms and bowel movements."},
    {"Medication": "Levothyroxine", "Dose": "100mcg", "When": "Once daily before food", "What it is for": "Thyroid hormone replacement", "Notes": "Usually taken before food."},
    {"Medication": "Omeprazole", "Dose": "20mg", "When": "Once daily", "What it is for": "Stomach acid protection", "Notes": ""},
    {"Medication": "Renapro powder", "Dose": "As prescribed", "When": "Usually mixed with drinks", "What it is for": "Protein / nutritional support", "Notes": "Can be mixed with coffee if tolerated."},
    {"Medication": "Rifaximin", "Dose": "550mg", "When": "Twice daily", "What it is for": "Hepatic encephalopathy support", "Notes": ""},
    {"Medication": "Thiamine", "Dose": "100mg", "When": "Twice daily", "What it is for": "Vitamin B1 support", "Notes": ""},
]

DEFAULT_APPOINTMENTS = [
    {
        "Date": "2026-06-16",
        "Clinic / Service": "Liver Transplant Review",
        "Location": "QE Birmingham",
        "Summary": "Still suitable for transplant. Strength and muscle mass acceptable. Bloods mostly okay. Low iron noted, iron infusion being arranged. Consultant felt mental and emotional difficulties were understandable. Psychology referral available if needed.",
        "Follow up / Actions": "Await iron infusion appointment. Continue tracking health data.",
    },
]


# ============================================================
# Environment helpers
# ============================================================

def load_env_file(path):
    env = {}

    if not os.path.exists(path):
        return env

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return env

    return env


LOCAL_ENV = load_env_file(ENV_FILE)


def get_secret_or_env(key, default=""):
    """
    Read settings from Streamlit Cloud Secrets, environment variables,
    or the local .env file, in that order.
    """
    try:
        if key in st.secrets:
            value = st.secrets.get(key)

            if value is not None:
                return str(value)
    except Exception:
        pass

    return os.getenv(key) or LOCAL_ENV.get(key, default)


def using_streamlit_cloud():
    try:
        return bool(st.secrets)
    except Exception:
        return False


WITHINGS_CLIENT_ID = get_secret_or_env("WITHINGS_CLIENT_ID", "")
WITHINGS_CLIENT_SECRET = get_secret_or_env("WITHINGS_CLIENT_SECRET", "")
WITHINGS_REDIRECT_URI = get_secret_or_env("WITHINGS_REDIRECT_URI", "http://localhost:8501")
WITHINGS_TOKENS_JSON = get_secret_or_env("WITHINGS_TOKENS_JSON", "")
APP_USERNAME = get_secret_or_env("APP_USERNAME", "Karl")
APP_PASSWORD = get_secret_or_env("APP_PASSWORD", "")
DASHBOARD_COOKIE_KEY = get_secret_or_env("DASHBOARD_COOKIE_KEY", get_secret_or_env("APP_COOKIE_KEY", ""))
DASHBOARD_REMEMBER_COOKIE = get_secret_or_env("DASHBOARD_REMEMBER_COOKIE", "karls_health_dashboard_remember")
DASHBOARD_REMEMBER_DAYS_RAW = get_secret_or_env("DASHBOARD_REMEMBER_DAYS", "30")

try:
    DASHBOARD_REMEMBER_DAYS = int(str(DASHBOARD_REMEMBER_DAYS_RAW).strip())
except Exception:
    DASHBOARD_REMEMBER_DAYS = 30

if DASHBOARD_REMEMBER_DAYS < 1:
    DASHBOARD_REMEMBER_DAYS = 30

GOOGLE_CLIENT_SECRET_JSON = get_secret_or_env("GOOGLE_CLIENT_SECRET_JSON", "")
GOOGLE_DRIVE_TOKEN_JSON = get_secret_or_env("GOOGLE_DRIVE_TOKEN_JSON", "")
GOOGLE_DRIVE_ENABLED = get_secret_or_env("GOOGLE_DRIVE_ENABLED", "1")


# ============================================================
# Password protection
# ============================================================

def dashboard_cookie_signing_key():
    """
    A private key used to sign the remember-this-device cookie.
    Best option: set DASHBOARD_COOKIE_KEY in Streamlit Secrets.
    Fallback: APP_PASSWORD, so existing installs still work.
    """
    key = str(DASHBOARD_COOKIE_KEY or "").strip()

    if key:
        return key

    return str(APP_PASSWORD or "").strip()


def dashboard_remember_token():
    """
    Create a stable signed token for this dashboard login.
    If the password or cookie key changes, old remembered devices stop working.
    """
    key = dashboard_cookie_signing_key()

    if not key or not APP_USERNAME or not APP_PASSWORD:
        return ""

    message = f"{APP_TITLE}|{APP_USERNAME}|{APP_PASSWORD}|remember-device-v1"
    return hmac.new(
        key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_query_param_value(name):
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""

    if isinstance(value, list):
        return value[0] if value else ""

    return value or ""


def remove_login_query_params():
    """
    Remove only the temporary login helper query params.
    Do not clear the whole URL, because Withings OAuth uses its own code params.
    """
    try:
        for key in ["_kh_remember_token", "_kh_cookie_checked"]:
            if key in st.query_params:
                del st.query_params[key]
    except Exception:
        pass


def remember_cookie_reader_script():
    """
    On iPhone/Safari, read our remember cookie and pass it back to Streamlit
    through a temporary query parameter. The app removes it after checking.
    """
    cookie_name = json.dumps(DASHBOARD_REMEMBER_COOKIE)

    components.html(
        f"""
        <script>
        (function() {{
            const cookieName = {cookie_name};

            function getCookie(name) {{
                const parts = document.cookie.split(';').map(function(item) {{
                    return item.trim();
                }});

                for (const part of parts) {{
                    if (part.startsWith(name + '=')) {{
                        return decodeURIComponent(part.substring(name.length + 1));
                    }}
                }}

                return '';
            }}

            try {{
                const parentUrl = new URL(window.parent.location.href);
                const alreadyChecked = parentUrl.searchParams.get('_kh_cookie_checked');

                if (alreadyChecked !== '1') {{
                    const token = getCookie(cookieName);

                    parentUrl.searchParams.set('_kh_cookie_checked', '1');

                    if (token) {{
                        parentUrl.searchParams.set('_kh_remember_token', token);
                    }}

                    window.parent.location.replace(parentUrl.toString());
                }}
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def remember_cookie_writer_script(token):
    """
    Save the remember-this-device cookie without reloading the page.
    Reloading immediately after login can create a login loop on Streamlit Cloud.
    """
    cookie_name = json.dumps(DASHBOARD_REMEMBER_COOKIE)
    cookie_value = json.dumps(token)
    max_age_seconds = int(DASHBOARD_REMEMBER_DAYS) * 24 * 60 * 60

    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const cookieName = {cookie_name};
                const cookieValue = encodeURIComponent({cookie_value});
                const maxAge = {max_age_seconds};

                document.cookie =
                    cookieName + '=' + cookieValue +
                    '; Max-Age=' + maxAge +
                    '; Path=/' +
                    '; SameSite=Lax' +
                    (window.location.protocol === 'https:' ? '; Secure' : '');
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def remember_cookie_clear_script():
    """
    Clear the remember-this-device cookie and reload the app.
    """
    cookie_name = json.dumps(DASHBOARD_REMEMBER_COOKIE)

    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const cookieName = {cookie_name};

                document.cookie =
                    cookieName + '=;' +
                    ' Max-Age=0;' +
                    ' Path=/;' +
                    ' SameSite=Lax' +
                    (window.location.protocol === 'https:' ? '; Secure' : '');

                const parentUrl = new URL(window.parent.location.href);
                parentUrl.searchParams.delete('_kh_remember_token');
                parentUrl.searchParams.delete('_kh_cookie_checked');

                window.parent.location.replace(parentUrl.toString());
            }} catch (e) {{
                window.parent.location.reload();
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def check_remembered_device():
    expected_token = dashboard_remember_token()
    supplied_token = get_query_param_value("_kh_remember_token")

    if expected_token and supplied_token and hmac.compare_digest(supplied_token, expected_token):
        st.session_state["dashboard_unlocked"] = True
        remove_login_query_params()
        st.rerun()

    remember_cookie_reader_script()


def check_dashboard_login():
    """
    Stop the dashboard loading until the correct username and password are entered.
    Username and password are read from Streamlit Secrets / environment / .env as
    APP_USERNAME and APP_PASSWORD.

    The optional "Remember this device" checkbox saves a signed browser cookie.
    This makes iPhone/Safari much less annoying because it can skip the login page
    after the first successful login.
    """
    username_required = bool(str(APP_USERNAME).strip())
    password_required = bool(str(APP_PASSWORD).strip())

    if not password_required:
        st.warning(
            "Dashboard password is not set. Add APP_PASSWORD to Streamlit Secrets to protect this app."
        )
        return

    if not username_required:
        st.warning(
            "Dashboard username is not set. Add APP_USERNAME to Streamlit Secrets to protect this app."
        )
        return

    if st.session_state.get("dashboard_unlocked", False):
        return

    check_remembered_device()

    login_area = st.empty()

    with login_area.container():
        st.title(APP_TITLE)
        st.caption("Private dashboard. Please enter your username and password to continue.")

        with st.form("dashboard_login_form"):
            entered_username = st.text_input("Username")
            entered_password = st.text_input("Password", type="password")
            remember_device = st.checkbox(
                f"Remember this device for {DASHBOARD_REMEMBER_DAYS} days",
                value=True,
                help="Good for your own iPhone or PC. Do not tick this on a shared device.",
            )
            submitted = st.form_submit_button("Unlock Dashboard")

    if submitted:
        username_ok = entered_username.strip().lower() == str(APP_USERNAME).strip().lower()
        password_ok = entered_password == str(APP_PASSWORD)

        if username_ok and password_ok:
            st.session_state["dashboard_unlocked"] = True

            if remember_device:
                token = dashboard_remember_token()

                if token:
                    remember_cookie_writer_script(token)
                    st.success("Login saved on this device.")

            # Clear the login box from the page before drawing the dashboard below.
            # This avoids showing the login form and the dashboard at the same time
            # on the first successful login.
            login_area.empty()
            return
        else:
            st.error("Username or password incorrect. Please try again.")

    st.stop()


check_dashboard_login()

# ============================================================
# General helpers
# ============================================================

def today_date():
    return date.today()


def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def load_json_file(path, default):
    if not os.path.exists(path):
        if path == GOALS_FILE:
            restore_local_file_from_google_drive_if_missing(
                GOALS_FILE,
                GOOGLE_DRIVE_GOALS_FILENAME,
            )

    if not os.path.exists(path):
        return default.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        merged = default.copy()
        merged.update(data)
        return merged
    except Exception:
        return default.copy()


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if path == GOALS_FILE:
        backup_local_file_to_google_drive(
            GOALS_FILE,
            GOOGLE_DRIVE_GOALS_FILENAME,
            "application/json",
        )


def human_duration_from_hours(hours):
    if hours is None or pd.isna(hours):
        return "No data"

    total_minutes = int(round(float(hours) * 60))
    h = total_minutes // 60
    m = total_minutes % 60

    if h <= 0:
        return f"{m} minutes"

    if m == 0:
        return f"{h} hours"

    return f"{h} hours {m} minutes"


def human_duration_short_from_hours(hours):
    if hours is None or pd.isna(hours):
        return "No data"

    total_minutes = int(round(float(hours) * 60))
    h = total_minutes // 60
    m = total_minutes % 60

    return f"{h}h {m}m"


def kg_to_st_lb(kg):
    if kg is None or pd.isna(kg):
        return "No data"

    total_lb = float(kg) * 2.2046226218
    stones = int(total_lb // 14)
    pounds = round(total_lb - (stones * 14), 1)

    return f"{stones}st {pounds}lb"


def stones_to_kg(stones):
    return float(stones) * 6.35029318


def pounds_to_st_lb_change(lb):
    if lb is None or pd.isna(lb):
        return "No data"

    sign = "+" if lb > 0 else "-" if lb < 0 else ""
    abs_lb = abs(float(lb))
    stones = int(abs_lb // 14)
    pounds = round(abs_lb - (stones * 14), 1)

    if stones == 0:
        return f"{sign}{pounds}lb"

    return f"{sign}{stones}st {pounds}lb"


def trend_arrow(value, lower_is_better=False):
    if value is None or pd.isna(value):
        return "→"

    if abs(value) < 0.01:
        return "→"

    if lower_is_better:
        return "↓" if value < 0 else "↑"

    return "↑" if value > 0 else "↓"


def compare_first_last_half(df, value_col):
    if df is None or df.empty or value_col not in df.columns:
        return None, None, None

    temp = df.copy()
    temp = temp.dropna(subset=[value_col])

    if temp.empty:
        return None, None, None

    temp = temp.sort_values("date")

    if len(temp) < 2:
        avg_value = temp[value_col].mean()
        return avg_value, avg_value, 0.0

    midpoint = len(temp) // 2

    first_half = temp.iloc[:midpoint]
    second_half = temp.iloc[midpoint:]

    first_avg = first_half[value_col].mean()
    second_avg = second_half[value_col].mean()
    change = second_avg - first_avg

    return first_avg, second_avg, change


def status_badge(value, target, higher_is_better=True, amber_margin=0.10):
    if value is None or pd.isna(value):
        return "⚪ No data", "No data available"

    value = float(value)
    target = float(target)

    if target == 0:
        return "⚪ No target", "No target set"

    if higher_is_better:
        if value >= target:
            return "🟢 On target", "At or above target"
        if value >= target * (1 - amber_margin):
            return "🟠 Slightly low", "Close to target"
        return "🔴 Below target", "Below target"

    if value <= target:
        return "🟢 On target", "At or below target"
    if value <= target * (1 + amber_margin):
        return "🟠 Slightly high", "Close to target"
    return "🔴 Above target", "Above target"


def small_warning(label, value_text):
    st.caption(f"**{label}:** {value_text}")


def date_range_from_days(days):
    end = today_date()
    start = end - timedelta(days=int(days) - 1)
    return start, end


def selected_range_label(days):
    labels = {
        1: "1 Day",
        2: "2 Days",
        3: "3 Days",
        7: "7 Days",
        14: "14 Days",
        21: "21 Days",
        28: "28 Days",
        42: "6 Weeks",
        60: "2 Months",
        90: "3 Months",
    }

    return labels.get(days, f"{days} Days")


def normalise_date_column(df, possible_columns):
    for col in possible_columns:
        if col in df.columns:
            df["date"] = pd.to_datetime(df[col], errors="coerce").dt.date
            return df

    return df


def filter_by_date(df, start_date, end_date):
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()

    temp = df.copy()
    temp = temp.dropna(subset=["date"])

    return temp[(temp["date"] >= start_date) & (temp["date"] <= end_date)].copy()


def metric_card(label, value, help_text=None, delta=None):
    st.metric(label, value, delta=delta, help=help_text)


def show_trend_card(title, main_text, detail_text, status_text):
    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(128,128,128,0.22);
            border-radius: 12px;
            padding: 0.75rem 0.85rem;
            margin-bottom: 0.55rem;
            background-color: rgba(128,128,128,0.05);
            min-height: 108px;
        ">
            <div style="font-size:0.85rem; opacity:0.75;">{title}</div>
            <div style="font-size:1.25rem; font-weight:700; margin-top:0.25rem;">{main_text}</div>
            <div style="font-size:0.85rem; margin-top:0.35rem;">{detail_text}</div>
            <div style="font-size:0.8rem; opacity:0.75; margin-top:0.25rem;">{status_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Chart helpers
# ============================================================

def simple_bar_chart(df, x, y, title, chart_key=None):
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        st.info("No data available for this chart.")
        return

    fig = px.bar(df, x=x, y=y, title=title)
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=50, b=20))

    if chart_key is None:
        chart_key = f"bar_{title}_{x}_{y}"

    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def simple_line_chart(df, x, y, title, chart_key=None):
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        st.info("No data available for this chart.")
        return

    fig = px.line(df, x=x, y=y, markers=True, title=title)
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=50, b=20))

    if chart_key is None:
        chart_key = f"line_{title}_{x}_{y}"

    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def macro_pie_chart(protein, carbs, fat, chart_key=None):
    protein_value = max(0.0, safe_float(protein))
    carbs_value = max(0.0, safe_float(carbs))
    fat_value = max(0.0, safe_float(fat))

    total = protein_value + carbs_value + fat_value

    if total <= 0:
        st.info("No macro data available.")
        return

    def format_grams(value):
        if abs(value - round(value)) < 0.05:
            return f"{int(round(value))}g"
        return f"{value:.1f}g"

    def percentage_list(values):
        raw = [v / total * 100 for v in values]
        rounded = [int(round(v)) for v in raw]
        diff = 100 - sum(rounded)

        if diff != 0:
            order = sorted(range(len(raw)), key=lambda i: raw[i] - int(raw[i]), reverse=(diff > 0))
            for i in range(abs(diff)):
                rounded[order[i % len(order)]] += 1 if diff > 0 else -1

        return rounded

    def polar(cx, cy, radius, angle_deg):
        import math

        rad = math.radians(angle_deg)
        x = cx + radius * math.cos(rad)
        y = cy + radius * math.sin(rad)
        return x, y

    def sector_path(cx, cy, radius, start_angle, end_angle):
        x1, y1 = polar(cx, cy, radius, start_angle)
        x2, y2 = polar(cx, cy, radius, end_angle)
        large_arc = 1 if end_angle - start_angle > 180 else 0
        return (
            f"M {cx:.2f} {cy:.2f} "
            f"L {x1:.2f} {y1:.2f} "
            f"A {radius:.2f} {radius:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z"
        )

    colors = {
        "carbs": "#63B892",
        "protein": "#9072D8",
        "fat": "#DABC57",
        "value": "#3E475B",
    }

    percentages = percentage_list([carbs_value, protein_value, fat_value])
    carbs_pct, protein_pct, fat_pct = percentages

    slices = [
        ("carbs", carbs_value, colors["carbs"]),
        ("protein", protein_value, colors["protein"]),
        ("fat", fat_value, colors["fat"]),
    ]

    start_angle = -90
    paths = []

    for _, value, color in slices:
        angle = (value / total) * 360
        end_angle = start_angle + angle
        paths.append(
            f'<path d="{sector_path(150, 150, 118, start_angle, end_angle)}" fill="{color}" stroke="#F4F4F4" stroke-width="4"></path>'
        )
        start_angle = end_angle

    svg = "".join(paths)

    html = f"""
    <div style="display:flex; align-items:center; justify-content:space-between; gap:1.5rem; flex-wrap:wrap; margin-top:0.25rem;">
        <div style="position:relative; width:360px; min-width:280px; height:290px;">
            <div style="position:absolute; left:0px; top:0px; color:{colors['fat']}; font-size:2.5rem; font-weight:600; line-height:1;">{fat_pct}%</div>
            <div style="position:absolute; left:12px; bottom:8px; color:{colors['protein']}; font-size:2.45rem; font-weight:600; line-height:1;">{protein_pct}%</div>
            <div style="position:absolute; right:0px; top:0px; color:{colors['carbs']}; font-size:2.5rem; font-weight:600; line-height:1;">{carbs_pct}%</div>
            <svg viewBox="0 0 300 300" style="position:absolute; left:38px; top:18px; width:235px; height:235px; overflow:visible;">
                {svg}
            </svg>
        </div>
        <div style="flex:1; min-width:240px; max-width:420px;">
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:1rem; gap:1rem;">
                <div style="color:{colors['carbs']}; font-size:2.2rem; font-weight:500; line-height:1.1;">T. Carbs</div>
                <div style="color:{colors['value']}; font-size:2.0rem; font-weight:600; line-height:1.1;">{format_grams(carbs_value)}</div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:1rem; gap:1rem;">
                <div style="color:{colors['protein']}; font-size:2.2rem; font-weight:500; line-height:1.1;">Protein</div>
                <div style="color:{colors['value']}; font-size:2.0rem; font-weight:600; line-height:1.1;">{format_grams(protein_value)}</div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:baseline; gap:1rem;">
                <div style="color:{colors['fat']}; font-size:2.2rem; font-weight:500; line-height:1.1;">Fat</div>
                <div style="color:{colors['value']}; font-size:2.0rem; font-weight:600; line-height:1.1;">{format_grams(fat_value)}</div>
            </div>
        </div>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)

def health_notes_line_chart(df, y_col, title, chart_key):
    if df is None or df.empty or y_col not in df.columns:
        st.info("No data available for this chart.")
        return

    temp = df.copy()
    temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
    temp = temp.dropna(subset=["date", y_col])

    if temp.empty:
        st.info("No numeric data available for this chart.")
        return

    temp = temp.sort_values("date")

    fig = px.line(temp, x="date", y=y_col, markers=True, title=title)
    fig.update_yaxes(range=[0, 10])
    fig.update_layout(height=330, margin=dict(l=20, r=20, t=50, b=20))

    st.plotly_chart(fig, use_container_width=True, key=chart_key)




# ============================================================
# Google Drive token backup helpers
# ============================================================

def google_drive_enabled():
    return str(GOOGLE_DRIVE_ENABLED).strip().lower() not in ["0", "false", "no", "off"]


def google_drive_client_config():
    """
    Returns Google OAuth client config from Streamlit Secrets or local JSON file.
    Local file expected: google_client_secret.json
    Optional Streamlit Secret: GOOGLE_CLIENT_SECRET_JSON
    """
    if not GOOGLE_DRIVE_LIBS_AVAILABLE:
        return None, "Google Drive Python packages are not installed."

    raw_client_secret = str(GOOGLE_CLIENT_SECRET_JSON or "").strip()

    if raw_client_secret:
        try:
            config = json.loads(raw_client_secret)
            if isinstance(config, dict) and ("installed" in config or "web" in config):
                return config, None
            return None, "GOOGLE_CLIENT_SECRET_JSON is not a valid Google OAuth JSON object."
        except Exception as e:
            return None, f"Could not read GOOGLE_CLIENT_SECRET_JSON: {e}"

    if os.path.exists(GOOGLE_CLIENT_SECRET_FILE):
        try:
            with open(GOOGLE_CLIENT_SECRET_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            if isinstance(config, dict) and ("installed" in config or "web" in config):
                return config, None

            return None, "google_client_secret.json was found but does not look like a full Google OAuth JSON file."
        except Exception as e:
            return None, f"Could not read google_client_secret.json: {e}"

    return None, "google_client_secret.json not found and GOOGLE_CLIENT_SECRET_JSON not set."


def load_google_drive_credentials():
    """
    Load Google Drive OAuth credentials from Streamlit Secrets or local google_drive_token.json.
    Refreshes the token if possible.
    """
    if not google_drive_enabled():
        return None, "Google Drive backup is disabled."

    if not GOOGLE_DRIVE_LIBS_AVAILABLE:
        return None, "Google Drive Python packages are not installed."

    creds = None

    raw_token = str(GOOGLE_DRIVE_TOKEN_JSON or "").strip()

    if raw_token:
        try:
            token_info = json.loads(raw_token)
            creds = GoogleCredentials.from_authorized_user_info(token_info, GOOGLE_DRIVE_SCOPES)
        except Exception as e:
            return None, f"Could not read GOOGLE_DRIVE_TOKEN_JSON: {e}"

    if creds is None and os.path.exists(GOOGLE_DRIVE_TOKEN_FILE):
        try:
            creds = GoogleCredentials.from_authorized_user_file(GOOGLE_DRIVE_TOKEN_FILE, GOOGLE_DRIVE_SCOPES)
        except Exception as e:
            return None, f"Could not read google_drive_token.json: {e}"

    if creds is None:
        return None, "Google Drive is not connected yet."

    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())

            try:
                with open(GOOGLE_DRIVE_TOKEN_FILE, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
            except Exception:
                pass

        if not creds.valid:
            return None, "Google Drive credentials are not valid. Reconnect Google Drive."

        return creds, None
    except Exception as e:
        return None, f"Google Drive credential refresh failed: {e}"


def connect_google_drive_locally():
    """
    Starts a local browser OAuth flow and saves google_drive_token.json.
    This is intended for running the app on Karl's Windows computer.
    """
    if not GOOGLE_DRIVE_LIBS_AVAILABLE:
        return False, "Google Drive Python packages are not installed."

    config, config_error = google_drive_client_config()

    if config_error:
        return False, config_error

    try:
        flow = InstalledAppFlow.from_client_config(config, GOOGLE_DRIVE_SCOPES)
        creds = flow.run_local_server(port=0)

        with open(GOOGLE_DRIVE_TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

        return True, "Google Drive connected. google_drive_token.json has been saved locally."
    except Exception as e:
        return False, f"Google Drive connection failed: {e}"


def get_google_drive_service():
    creds, creds_error = load_google_drive_credentials()

    if creds_error:
        return None, creds_error

    try:
        service = google_build("drive", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Could not build Google Drive service: {e}"


def find_google_drive_file_id(service, filename):
    try:
        safe_name = str(filename).replace("'", "\\'")
        query = f"name = '{safe_name}' and trashed = false"

        results = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, modifiedTime)",
            pageSize=10,
        ).execute()

        files = results.get("files", [])

        if not files:
            return None

        files = sorted(files, key=lambda x: x.get("modifiedTime", ""), reverse=True)
        return files[0].get("id")
    except Exception:
        return None


def upload_json_to_google_drive(filename, data):
    if not google_drive_enabled():
        return False, "Google Drive backup is disabled."

    service, service_error = get_google_drive_service()

    if service_error:
        return False, service_error

    try:
        content = json.dumps(data, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(BytesIO(content), mimetype="application/json", resumable=False)

        existing_file_id = find_google_drive_file_id(service, filename)

        if existing_file_id:
            service.files().update(
                fileId=existing_file_id,
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()
        else:
            service.files().create(
                body={
                    "name": filename,
                    "mimeType": "application/json",
                },
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()

        return True, "Uploaded to Google Drive."
    except Exception as e:
        return False, f"Google Drive upload failed: {e}"


def download_json_from_google_drive(filename):
    if not google_drive_enabled():
        return None, "Google Drive backup is disabled."

    service, service_error = get_google_drive_service()

    if service_error:
        return None, service_error

    try:
        file_id = find_google_drive_file_id(service, filename)

        if not file_id:
            return None, "No Google Drive backup file found."

        request = service.files().get_media(fileId=file_id)
        file_buffer = BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()

        file_buffer.seek(0)
        data = json.loads(file_buffer.read().decode("utf-8"))

        return data, None
    except Exception as e:
        return None, f"Google Drive download failed: {e}"


def upload_binary_to_google_drive(filename, content_bytes, mimetype="application/octet-stream"):
    if not google_drive_enabled():
        return False, "Google Drive backup is disabled."

    service, service_error = get_google_drive_service()

    if service_error:
        return False, service_error

    try:
        media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype=mimetype, resumable=False)
        existing_file_id = find_google_drive_file_id(service, filename)

        body = {
            "name": filename,
            "mimeType": mimetype,
        }

        if existing_file_id:
            service.files().update(
                fileId=existing_file_id,
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()
        else:
            service.files().create(
                body=body,
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()

        return True, f"Uploaded {filename} to Google Drive."
    except Exception as e:
        return False, f"Google Drive file upload failed for {filename}: {e}"


def download_binary_from_google_drive(filename):
    if not google_drive_enabled():
        return None, "Google Drive backup is disabled."

    service, service_error = get_google_drive_service()

    if service_error:
        return None, service_error

    try:
        file_id = find_google_drive_file_id(service, filename)

        if not file_id:
            return None, f"No Google Drive file found called {filename}."

        request = service.files().get_media(fileId=file_id)
        file_buffer = BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()

        file_buffer.seek(0)
        return file_buffer.read(), None
    except Exception as e:
        return None, f"Google Drive file download failed for {filename}: {e}"


def restore_local_file_from_google_drive_if_missing(local_path, drive_filename):
    """
    Restore a dashboard file from Google Drive only if it is missing locally.
    This is important for Streamlit Cloud, where local files can disappear after reboot.
    """
    if os.path.exists(local_path):
        return False, "Local file already exists."

    content_bytes, error = download_binary_from_google_drive(drive_filename)

    if error or content_bytes is None:
        return False, error or f"No Google Drive file found called {drive_filename}."

    try:
        with open(local_path, "wb") as f:
            f.write(content_bytes)

        return True, f"Restored {os.path.basename(local_path)} from Google Drive."
    except Exception as e:
        return False, f"Could not restore {os.path.basename(local_path)} locally: {e}"


def backup_local_file_to_google_drive(local_path, drive_filename, mimetype="application/octet-stream"):
    """
    Back up a local dashboard file to Google Drive.
    Used for goals, health notes, medications and appointments.
    """
    if not os.path.exists(local_path):
        return False, f"Local file not found: {os.path.basename(local_path)}"

    try:
        with open(local_path, "rb") as f:
            content_bytes = f.read()

        return upload_binary_to_google_drive(drive_filename, content_bytes, mimetype=mimetype)
    except Exception as e:
        return False, f"Could not back up {os.path.basename(local_path)} to Google Drive: {e}"


def backup_dashboard_editable_files_to_google_drive():
    """
    Back up the dashboard's small editable files to Google Drive.
    """
    results = []

    files_to_backup = [
        (GOALS_FILE, GOOGLE_DRIVE_GOALS_FILENAME, "application/json"),
        (HEALTH_NOTES_FILE, GOOGLE_DRIVE_HEALTH_NOTES_FILENAME, "text/csv"),
        (MEDICATIONS_FILE, GOOGLE_DRIVE_MEDICATIONS_FILENAME, "text/csv"),
        (APPOINTMENTS_FILE, GOOGLE_DRIVE_APPOINTMENTS_FILENAME, "text/csv"),
    ]

    for local_path, drive_filename, mimetype in files_to_backup:
        ok, message = backup_local_file_to_google_drive(local_path, drive_filename, mimetype)
        results.append({"File": os.path.basename(local_path), "Saved": ok, "Message": message})

    return results


def restore_dashboard_editable_files_from_google_drive(force=False):
    """
    Restore small editable dashboard files from Google Drive.

    If force=False, files are restored only when missing locally.
    If force=True, Google Drive versions overwrite local files.
    """
    results = []

    files_to_restore = [
        (GOALS_FILE, GOOGLE_DRIVE_GOALS_FILENAME),
        (HEALTH_NOTES_FILE, GOOGLE_DRIVE_HEALTH_NOTES_FILENAME),
        (MEDICATIONS_FILE, GOOGLE_DRIVE_MEDICATIONS_FILENAME),
        (APPOINTMENTS_FILE, GOOGLE_DRIVE_APPOINTMENTS_FILENAME),
    ]

    for local_path, drive_filename in files_to_restore:
        if force and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

        ok, message = restore_local_file_from_google_drive_if_missing(local_path, drive_filename)
        results.append({"File": os.path.basename(local_path), "Restored": ok, "Message": message})

    return results


def google_drive_editable_file_status(service):
    rows = []

    files_to_check = [
        ("Goals", GOOGLE_DRIVE_GOALS_FILENAME),
        ("Health notes", GOOGLE_DRIVE_HEALTH_NOTES_FILENAME),
        ("Medication list", GOOGLE_DRIVE_MEDICATIONS_FILENAME),
        ("Appointments", GOOGLE_DRIVE_APPOINTMENTS_FILENAME),
    ]

    for label, drive_filename in files_to_check:
        found = False

        if service is not None:
            found = bool(find_google_drive_file_id(service, drive_filename))

        rows.append(
            {
                "Check": f"{label} backup in Google Drive",
                "Status": "Found" if found else "Missing",
            }
        )

    return rows


def safe_google_drive_food_filename(original_name):
    base_name = os.path.basename(str(original_name or "food_export.xls"))
    safe_name = "".join(c if c.isalnum() or c in ["-", "_", ".", " "] else "_" for c in base_name)
    safe_name = safe_name.strip() or "food_export.xls"

    return GOOGLE_DRIVE_FOOD_PREFIX + safe_name


def original_food_filename_from_drive_name(drive_name):
    name = str(drive_name or "")

    if name.startswith(GOOGLE_DRIVE_FOOD_PREFIX):
        return name[len(GOOGLE_DRIVE_FOOD_PREFIX):]

    return name


def list_google_drive_food_files():
    if not google_drive_enabled():
        return [], "Google Drive backup is disabled."

    service, service_error = get_google_drive_service()

    if service_error:
        return [], service_error

    try:
        query = f"name contains '{GOOGLE_DRIVE_FOOD_PREFIX}' and trashed = false"

        results = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, modifiedTime, size)",
            pageSize=100,
            orderBy="modifiedTime desc",
        ).execute()

        return results.get("files", []), None
    except Exception as e:
        return [], f"Could not list Google Drive food files: {e}"


def backup_food_file_to_google_drive(original_name, content_bytes):
    drive_name = safe_google_drive_food_filename(original_name)
    lower_name = str(original_name).lower()

    if lower_name.endswith(".xls"):
        mimetype = "application/vnd.ms-excel"
    elif lower_name.endswith(".xlsx"):
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        mimetype = "application/octet-stream"

    return upload_binary_to_google_drive(drive_name, content_bytes, mimetype=mimetype)


@st.cache_data(ttl=900)
def load_food_data_from_google_drive_cached(food_file_signature):
    food_files, list_error = list_google_drive_food_files()

    if list_error:
        return pd.DataFrame(), [], [list_error]

    if not food_files:
        return pd.DataFrame(), [], ["No MyNetDiary files found in Google Drive yet."]

    # Google Drive returns files ordered by modifiedTime desc,
    # so the first file is the newest saved/uploaded MyNetDiary export.
    newest_file = food_files[0]

    drive_name = newest_file.get("name", "")
    original_name = original_food_filename_from_drive_name(drive_name)
    modified_time = newest_file.get("modifiedTime", "")

    content_bytes, download_error = download_binary_from_google_drive(drive_name)

    if download_error or content_bytes is None:
        return (
            pd.DataFrame(),
            [],
            [download_error or f"Could not download newest MyNetDiary file: {original_name} from Google Drive."],
        )

    sources = [
        {
            "name": original_name,
            "path": None,
            "bytes": content_bytes,
        }
    ]

    food_df, files_seen, parse_messages = parse_mynetdiary_sources(sources)

    messages = [
        f"Using newest MyNetDiary file from Google Drive: {original_name}"
        + (f" modified {modified_time}" if modified_time else "")
    ]

    messages.extend(parse_messages)

    return food_df, files_seen, messages


def load_food_data_from_google_drive():
    food_files, list_error = list_google_drive_food_files()

    if list_error:
        return pd.DataFrame(), [], [list_error]

    signature = "|".join(
        [
            f"{item.get('name', '')}:{item.get('modifiedTime', '')}:{item.get('size', '')}"
            for item in food_files
        ]
    )

    return load_food_data_from_google_drive_cached(signature)




def backup_withings_tokens_to_google_drive(tokens):
    if not tokens or not isinstance(tokens, dict):
        return False, "No Withings token data to back up."

    return upload_json_to_google_drive(GOOGLE_DRIVE_WITHINGS_FILENAME, tokens)


def restore_withings_tokens_from_google_drive():
    data, error = download_json_from_google_drive(GOOGLE_DRIVE_WITHINGS_FILENAME)

    if error:
        return None, error

    if isinstance(data, dict) and data.get("refresh_token"):
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

        return data, "Restored Withings tokens from Google Drive."

    return None, "Google Drive backup did not contain a valid Withings refresh token."


def google_drive_status_rows():
    token_json_exists = os.path.exists(GOOGLE_DRIVE_TOKEN_FILE)
    client_secret_exists = os.path.exists(GOOGLE_CLIENT_SECRET_FILE)
    secret_client_exists = bool(str(GOOGLE_CLIENT_SECRET_JSON or "").strip())
    secret_token_exists = bool(str(GOOGLE_DRIVE_TOKEN_JSON or "").strip())

    service, service_error = get_google_drive_service()
    backup_file_found = False

    food_file_count = 0

    if service is not None:
        backup_file_found = bool(find_google_drive_file_id(service, GOOGLE_DRIVE_WITHINGS_FILENAME))

        try:
            food_files, food_error = list_google_drive_food_files()
            food_file_count = len(food_files)
        except Exception:
            food_file_count = 0

    rows = [
        {"Check": "Google Drive backup enabled", "Status": "Yes" if google_drive_enabled() else "No"},
        {"Check": "Google Drive packages", "Status": "Installed" if GOOGLE_DRIVE_LIBS_AVAILABLE else "Missing"},
        {"Check": "Google client secret file", "Status": "Found" if client_secret_exists else "Missing"},
        {"Check": "Google client secret in Secrets", "Status": "Found" if secret_client_exists else "Missing"},
        {"Check": "Google Drive token file", "Status": "Found" if token_json_exists else "Missing"},
        {"Check": "Google Drive token in Secrets", "Status": "Found" if secret_token_exists else "Missing"},
        {"Check": "Google Drive connection", "Status": "Working" if service is not None else service_error or "Not connected"},
        {"Check": "Withings token backup in Google Drive", "Status": "Found" if backup_file_found else "Missing"},
        {"Check": "Saved food files in Google Drive", "Status": str(food_file_count)},
    ]

    rows.extend(google_drive_editable_file_status(service))

    return rows


def google_drive_token_backup_text():
    if not os.path.exists(GOOGLE_DRIVE_TOKEN_FILE):
        return ""

    try:
        with open(GOOGLE_DRIVE_TOKEN_FILE, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        return (
            "GOOGLE_DRIVE_TOKEN_JSON = '''\n"
            + json.dumps(token_data, indent=2)
            + "\n'''"
        )
    except Exception:
        return ""


# ============================================================
# Withings OAuth and API helpers
# ============================================================

def load_tokens_from_secrets():
    """
    Load Withings tokens from Streamlit Cloud Secrets.

    Recommended Streamlit Secrets entry:

    WITHINGS_TOKENS_JSON = '''
    {
      "access_token": "...",
      "refresh_token": "...",
      "userid": "...",
      "scope": "user.info,user.metrics,user.activity",
      "token_type": "Bearer",
      "expires_in": 10800
    }
    '''
    """
    raw_tokens = WITHINGS_TOKENS_JSON

    if raw_tokens:
        try:
            parsed = json.loads(str(raw_tokens))

            if isinstance(parsed, dict) and parsed.get("refresh_token"):
                return parsed
        except Exception:
            return None

    # Optional fallback for individual secret keys, useful if preferred later.
    try:
        access_token = st.secrets.get("WITHINGS_ACCESS_TOKEN", "")
        refresh_token = st.secrets.get("WITHINGS_REFRESH_TOKEN", "")

        if refresh_token:
            tokens = {
                "access_token": str(access_token),
                "refresh_token": str(refresh_token),
                "scope": str(st.secrets.get("WITHINGS_SCOPE", WITHINGS_SCOPE)),
                "token_type": str(st.secrets.get("WITHINGS_TOKEN_TYPE", "Bearer")),
                "expires_in": safe_int(st.secrets.get("WITHINGS_EXPIRES_IN", 10800), 10800),
            }

            user_id = st.secrets.get("WITHINGS_USERID", "")

            if user_id:
                tokens["userid"] = str(user_id)

            return tokens
    except Exception:
        pass

    return None


def load_tokens():
    # 1) Local token file, fastest and best for Windows/local use.
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 2) Google Drive backup, useful after a reboot/cloud restart if local file is missing.
    drive_tokens, drive_message = restore_withings_tokens_from_google_drive()

    if drive_tokens:
        try:
            st.session_state["withings_drive_restore_message"] = drive_message
        except Exception:
            pass

        return drive_tokens

    try:
        st.session_state["withings_drive_restore_message"] = drive_message
    except Exception:
        pass

    # 3) Streamlit Secrets fallback, still supported.
    return load_tokens_from_secrets()


def save_tokens(tokens):
    # Store in the app session so the latest token can be used immediately.
    try:
        st.session_state["latest_withings_tokens"] = tokens
    except Exception:
        pass

    # Also write a local token file.
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
    except Exception:
        pass

    # Back up to Google Drive so the dashboard can restore after restart/cloud refresh.
    try:
        ok, message = backup_withings_tokens_to_google_drive(tokens)
        st.session_state["withings_drive_backup_message"] = message
        st.session_state["withings_drive_backup_ok"] = ok
    except Exception as e:
        try:
            st.session_state["withings_drive_backup_message"] = f"Google Drive backup failed: {e}"
            st.session_state["withings_drive_backup_ok"] = False
        except Exception:
            pass


def delete_tokens():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)

    try:
        st.session_state.pop("latest_withings_tokens", None)
    except Exception:
        pass


def build_withings_auth_url():
    params = {
        "response_type": "code",
        "client_id": WITHINGS_CLIENT_ID,
        "redirect_uri": WITHINGS_REDIRECT_URI,
        "scope": WITHINGS_SCOPE,
        "state": "karls_health_dashboard",
    }

    return f"{WITHINGS_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code):
    if not WITHINGS_CLIENT_ID or not WITHINGS_CLIENT_SECRET:
        return False, "Missing WITHINGS_CLIENT_ID or WITHINGS_CLIENT_SECRET in .env / Streamlit Secrets."

    data = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "code": code,
        "redirect_uri": WITHINGS_REDIRECT_URI,
    }

    try:
        response = requests.post(WITHINGS_TOKEN_URL, data=data, timeout=25)
        payload = response.json()

        if payload.get("status") == 0:
            tokens = payload.get("body", {})
            save_tokens(tokens)
            st.cache_data.clear()
            return True, "Withings connected successfully."

        return False, f"Withings token exchange failed: {payload}"
    except Exception as e:
        return False, f"Withings token exchange error: {e}"


def refresh_access_token_once(tokens):
    if not tokens:
        return None, "No token file loaded."

    refresh_token = tokens.get("refresh_token", "")

    if not refresh_token:
        return tokens, "Refresh token missing."

    if not WITHINGS_CLIENT_ID or not WITHINGS_CLIENT_SECRET:
        return tokens, "Missing WITHINGS_CLIENT_ID or WITHINGS_CLIENT_SECRET in .env / Streamlit Secrets, cannot refresh token."

    data = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(WITHINGS_TOKEN_URL, data=data, timeout=25)

        try:
            payload = response.json()
        except Exception:
            return tokens, f"Token refresh failed, non-JSON response: HTTP {response.status_code}, {response.text[:500]}"

        if payload.get("status") == 0:
            new_tokens = payload.get("body", {})
            save_tokens(new_tokens)
            return new_tokens, None

        if payload.get("status") == 601:
            return tokens, f"Token refresh rate limited by Withings: {payload}. Existing access token will be used if still valid."

        return tokens, f"Token refresh failed: {payload}"
    except Exception as e:
        return tokens, f"Token refresh error: {e}"


def get_runtime_withings_tokens():
    tokens = load_tokens()

    if not tokens:
        return None, "Withings is not connected yet."

    refreshed_tokens, refresh_error = refresh_access_token_once(tokens)

    if not refreshed_tokens:
        return None, refresh_error or "Could not load Withings tokens."

    return refreshed_tokens, refresh_error


def withings_get_with_access_token(endpoint, params, access_token):
    if not access_token:
        return None, "Withings access token missing.", None

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=25)

        try:
            payload = response.json()
        except Exception:
            return None, f"HTTP {response.status_code}, non-JSON response: {response.text[:500]}", None

        if payload.get("status") == 0:
            return payload.get("body", {}), None, payload

        return None, f"API returned error: {payload}", payload

    except Exception as e:
        return None, f"Withings API request error: {e}", None


def get_withings_status(sleep_df, activity_df, weight_df, errors, runtime_refresh_error):
    token_exists = os.path.exists(TOKEN_FILE)
    secret_token_exists = bool(WITHINGS_TOKENS_JSON)
    tokens = load_tokens()

    access_token_found = bool(tokens and tokens.get("access_token"))
    refresh_token_found = bool(tokens and tokens.get("refresh_token"))
    token_scope = tokens.get("scope", "") if tokens else ""

    env_exists = os.path.exists(ENV_FILE)
    client_id_found = bool(WITHINGS_CLIENT_ID)
    client_secret_found = bool(WITHINGS_CLIENT_SECRET)

    status_rows = [
        {"Check": ".env file", "Status": "Found" if env_exists else "Missing / not needed in cloud"},
        {"Check": "Streamlit Secrets", "Status": "Available" if using_streamlit_cloud() else "Not detected locally"},
        {"Check": "Client ID", "Status": "Found" if client_id_found else "Missing"},
        {"Check": "Client Secret", "Status": "Found" if client_secret_found else "Missing"},
        {"Check": "Token file", "Status": "Found" if token_exists else "Missing"},
        {"Check": "Token backup in Secrets", "Status": "Found" if secret_token_exists else "Missing"},
        {"Check": "Access token", "Status": "Found" if access_token_found else "Missing"},
        {"Check": "Refresh token", "Status": "Found" if refresh_token_found else "Missing"},
        {"Check": "Token scope", "Status": token_scope if token_scope else "No scope found"},
        {"Check": "Token refresh message", "Status": runtime_refresh_error or "None"},
        {"Check": "Sleep rows loaded", "Status": str(len(sleep_df)) if sleep_df is not None else "0"},
        {"Check": "Step rows loaded", "Status": str(len(activity_df)) if activity_df is not None else "0"},
        {"Check": "Weight rows loaded", "Status": str(len(weight_df)) if weight_df is not None else "0"},
        {"Check": "Sleep API error", "Status": errors.get("sleep") or "None"},
        {"Check": "Steps API error", "Status": errors.get("activity") or "None"},
        {"Check": "Weight API error", "Status": errors.get("weight") or "None"},
    ]

    status_rows.extend(google_drive_status_rows())

    return pd.DataFrame(status_rows)


def handle_withings_callback():
    try:
        query_params = st.query_params
    except Exception:
        query_params = {}

    code = query_params.get("code", None)
    error = query_params.get("error", None)

    if isinstance(code, list):
        code = code[0]

    if isinstance(error, list):
        error = error[0]

    if error:
        st.error(f"Withings returned an error: {error}")
        return

    if code:
        success, message = exchange_code_for_tokens(code)

        if success:
            st.success(message)

            try:
                st.query_params.clear()
            except Exception:
                pass
        else:
            st.error(message)


def get_withings_activity(start_date, end_date, access_token):
    endpoint = "https://wbsapi.withings.net/v2/measure"

    params = {
        "action": "getactivity",
        "startdateymd": start_date.strftime("%Y-%m-%d"),
        "enddateymd": end_date.strftime("%Y-%m-%d"),
    }

    body, error, raw = withings_get_with_access_token(endpoint, params, access_token)

    if error or not body:
        return pd.DataFrame(), error or "No body returned from activity API."

    rows = body.get("activities", [])

    if not rows:
        return pd.DataFrame(), f"No activity rows returned. Raw body: {body}"

    df = pd.DataFrame(rows)
    df = normalise_date_column(df, ["date", "day"])

    if "steps" not in df.columns:
        df["steps"] = 0

    return df, None


def get_withings_weight(start_date, end_date, access_token):
    endpoint = "https://wbsapi.withings.net/measure"

    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date + timedelta(days=1), datetime.min.time()).timestamp())

    params = {
        "action": "getmeas",
        "meastype": 1,
        "category": 1,
        "startdate": start_ts,
        "enddate": end_ts,
    }

    body, error, raw = withings_get_with_access_token(endpoint, params, access_token)

    if error or not body:
        return pd.DataFrame(), error or "No body returned from weight API."

    groups = body.get("measuregrps", [])

    if not groups:
        return pd.DataFrame(), f"No weight measure groups returned. Raw body: {body}"

    rows = []

    for group in groups:
        measure_date = datetime.fromtimestamp(group.get("date")).date()

        for measure in group.get("measures", []):
            if measure.get("type") == 1:
                value = measure.get("value", 0)
                unit = measure.get("unit", 0)
                kg = value * (10 ** unit)

                rows.append(
                    {
                        "date": measure_date,
                        "weight_kg": kg,
                        "weight_st_lb": kg_to_st_lb(kg),
                    }
                )

    if not rows:
        return pd.DataFrame(), f"No weight rows after parsing. Raw body: {body}"

    df = pd.DataFrame(rows)
    df = df.sort_values("date")

    return df, None


def get_withings_sleep(start_date, end_date, access_token):
    endpoint = "https://wbsapi.withings.net/v2/sleep"

    params = {
        "action": "getsummary",
        "startdateymd": start_date.strftime("%Y-%m-%d"),
        "enddateymd": end_date.strftime("%Y-%m-%d"),
        "data_fields": "total_sleep_time,wakeupduration,lightsleepduration,deepsleepduration,remsleepduration,hr_average,rr_average",
    }

    body, error, raw = withings_get_with_access_token(endpoint, params, access_token)

    if error or not body:
        return pd.DataFrame(), error or "No body returned from sleep API."

    series = body.get("series", [])

    if not series:
        return pd.DataFrame(), f"No sleep series returned. Raw body: {body}"

    rows = []

    for item in series:
        ymd = item.get("date")
        data = item.get("data", {})

        total_sleep_seconds = safe_float(data.get("total_sleep_time", 0), 0)
        total_sleep_hours = total_sleep_seconds / 3600

        startdate = item.get("startdate")
        enddate = item.get("enddate")

        start_time = ""
        end_time = ""

        if startdate:
            start_time = datetime.fromtimestamp(startdate).strftime("%H:%M")

        if enddate:
            end_time = datetime.fromtimestamp(enddate).strftime("%H:%M")

        rows.append(
            {
                "date": pd.to_datetime(ymd, errors="coerce").date(),
                "sleep_hours": total_sleep_hours,
                "sleep_text": human_duration_short_from_hours(total_sleep_hours),
                "start_time": start_time,
                "end_time": end_time,
                "average_hr": data.get("hr_average"),
                "average_rr": data.get("rr_average"),
            }
        )

    if not rows:
        return pd.DataFrame(), f"No sleep rows after parsing. Raw body: {body}"

    df = pd.DataFrame(rows)
    df = df.sort_values("date")

    return df, None


# ============================================================
# MyNetDiary food parser
# ============================================================

def _read_excel_sheets_from_source(source_name, source_bytes=None, source_path=None):
    """
    Read all sheets from either a local MyNetDiary file or an uploaded Streamlit file.
    Returns a dict of sheet_name -> raw preview dataframe.
    """
    try:
        engine = "xlrd" if str(source_name).lower().endswith(".xls") else None

        if source_bytes is not None:
            return pd.read_excel(
                BytesIO(source_bytes),
                sheet_name=None,
                header=None,
                engine=engine,
            )

        if source_path is not None:
            return pd.read_excel(
                source_path,
                sheet_name=None,
                header=None,
                engine=engine,
            )
    except Exception:
        return {}

    return {}


def _read_single_excel_sheet(source_name, sheet_name, header_row, source_bytes=None, source_path=None):
    """
    Read one sheet from either a local MyNetDiary file or an uploaded Streamlit file.
    """
    try:
        engine = "xlrd" if str(source_name).lower().endswith(".xls") else None

        if source_bytes is not None:
            return pd.read_excel(
                BytesIO(source_bytes),
                sheet_name=sheet_name,
                header=header_row,
                engine=engine,
            )

        if source_path is not None:
            return pd.read_excel(
                source_path,
                sheet_name=sheet_name,
                header=header_row,
                engine=engine,
            )
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame()


def parse_mynetdiary_sources(sources):
    """
    Parse MyNetDiary Excel exports.

    sources must be a list of dictionaries:
    {
        "name": "MyNetDiary_Year_2026.xls",
        "path": "...optional local path...",
        "bytes": b"...optional uploaded file bytes..."
    }
    """
    if not sources:
        return pd.DataFrame(), [], []

    all_rows = []
    files_seen = []
    parse_messages = []

    def clean_column_name(value):
        return str(value).strip().replace("\n", " ").replace("\r", " ")

    def find_header_row(preview_df):
        best_row = None
        best_score = 0

        keywords = [
            "date",
            "meal",
            "food",
            "name",
            "calories",
            "calorie",
            "kcal",
            "protein",
            "carb",
            "carbohydrate",
            "fat",
            "sugar",
            "sugars",
        ]

        for idx in range(min(40, len(preview_df))):
            row_values = " ".join(
                [
                    str(v).lower().strip()
                    for v in preview_df.iloc[idx].tolist()
                    if not pd.isna(v)
                ]
            )

            score = sum(1 for word in keywords if word in row_values)

            if score > best_score:
                best_score = score
                best_row = idx

        if best_score >= 3:
            return best_row

        return 0

    def find_col(columns, possible_names):
        lower_cols = {str(c).lower().strip(): c for c in columns}

        for name in possible_names:
            name_low = name.lower().strip()
            if name_low in lower_cols:
                return lower_cols[name_low]

        for c in columns:
            c_low = str(c).lower().strip()

            for name in possible_names:
                name_low = name.lower().strip()

                if name_low in c_low:
                    return c

        return None

    for source in sources:
        source_name = source.get("name", "Unknown file")
        source_path = source.get("path")
        source_bytes = source.get("bytes")

        files_seen.append(source_name)

        try:
            preview_sheets = _read_excel_sheets_from_source(
                source_name=source_name,
                source_bytes=source_bytes,
                source_path=source_path,
            )

            if not preview_sheets:
                parse_messages.append(f"{source_name}: could not read Excel sheets.")
                continue

            file_rows_before = len(all_rows)

            for sheet_name, preview_df in preview_sheets.items():
                if preview_df is None or preview_df.empty:
                    continue

                header_row = find_header_row(preview_df)

                df = _read_single_excel_sheet(
                    source_name=source_name,
                    sheet_name=sheet_name,
                    header_row=header_row,
                    source_bytes=source_bytes,
                    source_path=source_path,
                )

                if df is None or df.empty:
                    continue

                df = df.copy()
                df.columns = [clean_column_name(c) for c in df.columns]
                df = df.dropna(how="all")

                date_col = find_col(df.columns, ["Date", "Day", "Log Date", "Entry Date"])
                meal_col = find_col(df.columns, ["Meal", "Meal Name", "Meal Type"])
                food_col = find_col(df.columns, ["Food", "Food Name", "Name", "Item", "Description"])
                calories_col = find_col(df.columns, ["Calories", "Calorie", "Calories kcal", "Calories (kcal)", "Energy", "Energy kcal", "kcal"])
                protein_col = find_col(df.columns, ["Protein", "Protein g", "Protein (g)"])
                carbs_col = find_col(df.columns, ["Carbs", "Carb", "Carbohydrates", "Carbohydrate", "Total Carbohydrate", "Total Carbs", "Carbs g", "Carbs (g)"])
                fat_col = find_col(df.columns, ["Fat", "Total Fat", "Fat g", "Fat (g)"])
                sugar_col = find_col(df.columns, ["Sugar", "Sugars", "Sugar g", "Sugars g", "Sugar (g)", "Sugars (g)"])
                fluid_col = find_col(df.columns, ["Water", "Fluid", "Fluids", "Water ml", "Fluid ml", "Fluids ml", "Water (ml)", "Fluid (ml)", "Fluids (ml)", "Water, ml", "Fluid, ml", "Fluids, ml", "Total Water", "Total Fluids", "Hydration", "Liquid", "Liquids"])
                amount_col = find_col(df.columns, ["Amount", "Quantity", "Qty", "Serving", "Serving Size", "Servings", "Measure", "Unit", "Portion"])

                if not date_col:
                    continue

                clean = pd.DataFrame()

                clean["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
                clean["meal"] = df[meal_col].astype(str) if meal_col else "Unknown"
                clean["food"] = df[food_col].astype(str) if food_col else "Unknown food"

                clean["calories"] = pd.to_numeric(df[calories_col], errors="coerce") if calories_col else 0
                clean["protein_g"] = pd.to_numeric(df[protein_col], errors="coerce") if protein_col else 0
                clean["carbs_g"] = pd.to_numeric(df[carbs_col], errors="coerce") if carbs_col else 0
                clean["fat_g"] = pd.to_numeric(df[fat_col], errors="coerce") if fat_col else 0
                clean["sugar_g"] = pd.to_numeric(df[sugar_col], errors="coerce") if sugar_col else 0
                clean["fluid_ml"] = pd.to_numeric(df[fluid_col], errors="coerce") if fluid_col else 0

                if amount_col:
                    amount_text = df[amount_col].astype(str)
                    inferred_fluid = [
                        infer_fluid_ml_from_text(meal, food, amount)
                        for meal, food, amount in zip(clean["meal"], clean["food"], amount_text)
                    ]
                else:
                    inferred_fluid = [
                        infer_fluid_ml_from_text(meal, food)
                        for meal, food in zip(clean["meal"], clean["food"])
                    ]

                clean["fluid_ml"] = pd.to_numeric(clean["fluid_ml"], errors="coerce").fillna(0)
                clean["fluid_ml"] = clean["fluid_ml"].where(clean["fluid_ml"] > 0, inferred_fluid)

                clean["source_file"] = source_name
                clean["source_sheet"] = sheet_name
                clean["detected_header_row"] = header_row

                clean = clean.dropna(subset=["date"])
                clean = clean.fillna(0)

                clean = clean[
                    (clean["calories"] != 0)
                    | (clean["protein_g"] != 0)
                    | (clean["carbs_g"] != 0)
                    | (clean["fat_g"] != 0)
                    | (clean["food"].astype(str).str.lower() != "unknown food")
                ]

                if not clean.empty:
                    all_rows.append(clean)

            if len(all_rows) == file_rows_before:
                parse_messages.append(f"{source_name}: file was read, but no usable food rows were found.")

        except Exception as e:
            parse_messages.append(f"{source_name}: {e}")
            continue

    if not all_rows:
        return pd.DataFrame(), files_seen, parse_messages

    final_df = pd.concat(all_rows, ignore_index=True)

    final_df = final_df.drop_duplicates(
        subset=[
            "date",
            "meal",
            "food",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "sugar_g",
        ],
        keep="first",
    )

    final_df = final_df.sort_values("date")

    return final_df, files_seen, parse_messages


@st.cache_data(ttl=900)
def load_food_data_from_local_files():
    sources = []

    files = []
    files.extend(glob.glob(os.path.join(BASE_DIR, "MyNetDiary_Year_*.xls")))
    files.extend(glob.glob(os.path.join(BASE_DIR, "MyNetDiary_Year_*.xlsx")))
    files = sorted(list(set(files)), key=lambda p: os.path.getmtime(p), reverse=True)

    # Use only the newest local MyNetDiary export.
    # This means you can drop a new file into the app folder without replacing the old one.
    if files:
        newest_path = files[0]
        sources.append(
            {
                "name": os.path.basename(newest_path),
                "path": newest_path,
                "bytes": None,
            }
        )

    food_df, files_seen, parse_messages = parse_mynetdiary_sources(sources)

    if files_seen:
        parse_messages = [f"Using newest local MyNetDiary file: {files_seen[0]}"] + parse_messages

    return food_df, files_seen, parse_messages


@st.cache_data(ttl=900)
def load_food_data_from_uploads(uploaded_file_payloads):
    sources = []

    for item in uploaded_file_payloads:
        sources.append(
            {
                "name": item["name"],
                "path": None,
                "bytes": item["bytes"],
            }
        )

    food_df, files_seen, parse_messages = parse_mynetdiary_sources(sources)

    return food_df, files_seen, parse_messages


def load_food_data(uploaded_food_files=None):
    uploaded_payloads = []
    upload_messages = []

    if uploaded_food_files:
        for uploaded_file in uploaded_food_files:
            file_bytes = uploaded_file.getvalue()

            uploaded_payloads.append(
                {
                    "name": uploaded_file.name,
                    "bytes": file_bytes,
                }
            )

            ok, message = backup_food_file_to_google_drive(uploaded_file.name, file_bytes)

            if ok:
                upload_messages.append(message)
            else:
                upload_messages.append(message)

    if uploaded_payloads:
        food_df, files_seen, parse_messages = load_food_data_from_uploads(uploaded_payloads)
        return food_df, files_seen, upload_messages + parse_messages

    drive_food_df, drive_food_files, drive_food_messages = load_food_data_from_google_drive()

    if not drive_food_df.empty or drive_food_files:
        return drive_food_df, drive_food_files, drive_food_messages

    local_food_df, local_food_files, local_food_messages = load_food_data_from_local_files()

    if not local_food_df.empty or local_food_files:
        return local_food_df, local_food_files, local_food_messages

    return drive_food_df, drive_food_files, drive_food_messages


def food_daily_summary(food_df):
    if food_df is None or food_df.empty:
        return pd.DataFrame()

    daily = (
        food_df.groupby("date", as_index=False)
        .agg(
            calories=("calories", "sum"),
            protein_g=("protein_g", "sum"),
            carbs_g=("carbs_g", "sum"),
            fat_g=("fat_g", "sum"),
            sugar_g=("sugar_g", "sum"),
            fluid_ml=("fluid_ml", "sum"),
        )
        .sort_values("date")
    )

    return daily


def build_typical_food_day(food_df):
    if food_df is None or food_df.empty:
        return {}

    df = food_df.copy()

    df["meal"] = df["meal"].replace("nan", "Unknown")
    df["food"] = df["food"].replace("nan", "Unknown food")

    result = {}

    meal_order = [
        "Breakfast",
        "Lunch",
        "Dinner",
        "Evening Meal",
        "Snack",
        "Snacks",
        "Unknown",
    ]

    meals = list(df["meal"].dropna().unique())
    sorted_meals = []

    for preferred in meal_order:
        for meal in meals:
            if preferred.lower() in str(meal).lower() and meal not in sorted_meals:
                sorted_meals.append(meal)

    for meal in meals:
        if meal not in sorted_meals:
            sorted_meals.append(meal)

    for meal in sorted_meals:
        meal_df = df[df["meal"] == meal].copy()

        foods = (
            meal_df.groupby("food", as_index=False)
            .agg(
                times_seen=("food", "count"),
                avg_calories=("calories", "mean"),
                avg_protein=("protein_g", "mean"),
            )
            .sort_values(["times_seen", "avg_protein"], ascending=False)
            .head(6)
        )

        result[str(meal)] = foods

    return result


# ============================================================
# Local editable files
# ============================================================

def load_medications():
    restore_local_file_from_google_drive_if_missing(
        MEDICATIONS_FILE,
        GOOGLE_DRIVE_MEDICATIONS_FILENAME,
    )

    if os.path.exists(MEDICATIONS_FILE):
        try:
            return pd.read_csv(MEDICATIONS_FILE)
        except Exception:
            pass

    df = pd.DataFrame(DEFAULT_MEDICATIONS)
    df.to_csv(MEDICATIONS_FILE, index=False)
    backup_local_file_to_google_drive(MEDICATIONS_FILE, GOOGLE_DRIVE_MEDICATIONS_FILENAME, "text/csv")

    return df


def save_medications(df):
    df.to_csv(MEDICATIONS_FILE, index=False)
    backup_local_file_to_google_drive(MEDICATIONS_FILE, GOOGLE_DRIVE_MEDICATIONS_FILENAME, "text/csv")


def load_appointments():
    restore_local_file_from_google_drive_if_missing(
        APPOINTMENTS_FILE,
        GOOGLE_DRIVE_APPOINTMENTS_FILENAME,
    )

    if os.path.exists(APPOINTMENTS_FILE):
        try:
            df = pd.read_csv(APPOINTMENTS_FILE)

            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date.astype(str)

            return df
        except Exception:
            pass

    df = pd.DataFrame(DEFAULT_APPOINTMENTS)
    df.to_csv(APPOINTMENTS_FILE, index=False)
    backup_local_file_to_google_drive(APPOINTMENTS_FILE, GOOGLE_DRIVE_APPOINTMENTS_FILENAME, "text/csv")

    return df


def save_appointments(df):
    df.to_csv(APPOINTMENTS_FILE, index=False)
    backup_local_file_to_google_drive(APPOINTMENTS_FILE, GOOGLE_DRIVE_APPOINTMENTS_FILENAME, "text/csv")


def empty_health_notes_df():
    return pd.DataFrame(columns=HEALTH_NOTE_COLUMNS)


def clean_health_notes_df(df):
    if df is None or df.empty:
        return empty_health_notes_df()

    df = df.copy()

    for col in HEALTH_NOTE_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[HEALTH_NOTE_COLUMNS]

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date.astype(str)

    df = df[df["Date"].notna()]
    df = df[df["Date"] != "NaT"]

    # Remove fully blank rows apart from date
    value_cols = [c for c in HEALTH_NOTE_COLUMNS if c != "Date"]
    df[value_cols] = df[value_cols].fillna("")

    keep_mask = df[value_cols].astype(str).apply(
        lambda row: any(v.strip().lower() not in ["", "none", "nan"] for v in row),
        axis=1,
    )

    df = df[keep_mask].copy()

    # If there are duplicate dates, keep the latest row for that date
    df = df.drop_duplicates(subset=["Date"], keep="last")

    return df.sort_values("Date", ascending=False).reset_index(drop=True)


def load_health_notes():
    restore_local_file_from_google_drive_if_missing(
        HEALTH_NOTES_FILE,
        GOOGLE_DRIVE_HEALTH_NOTES_FILENAME,
    )

    if os.path.exists(HEALTH_NOTES_FILE):
        try:
            df = pd.read_csv(HEALTH_NOTES_FILE)
            df = clean_health_notes_df(df)
            df.to_csv(HEALTH_NOTES_FILE, index=False)
            backup_local_file_to_google_drive(HEALTH_NOTES_FILE, GOOGLE_DRIVE_HEALTH_NOTES_FILENAME, "text/csv")
            return df
        except Exception:
            pass

    df = empty_health_notes_df()
    df.to_csv(HEALTH_NOTES_FILE, index=False)
    backup_local_file_to_google_drive(HEALTH_NOTES_FILE, GOOGLE_DRIVE_HEALTH_NOTES_FILENAME, "text/csv")

    return df


def save_health_notes(df):
    clean_df = clean_health_notes_df(df)
    clean_df.to_csv(HEALTH_NOTES_FILE, index=False)
    backup_local_file_to_google_drive(HEALTH_NOTES_FILE, GOOGLE_DRIVE_HEALTH_NOTES_FILENAME, "text/csv")


def add_or_update_today_health_note(existing_df, new_row):
    df = clean_health_notes_df(existing_df)
    today_str = date.today().strftime("%Y-%m-%d")

    new_row["Date"] = today_str

    df = df[df["Date"] != today_str].copy()
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = clean_health_notes_df(df)

    save_health_notes(df)

    return df


def prepare_health_notes_for_charts(health_notes_df):
    if health_notes_df is None or health_notes_df.empty:
        return pd.DataFrame()

    df = clean_health_notes_df(health_notes_df)

    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

    for col in ["Pain 0-10", "Brain fog 0-10", "Fatigue 0-10"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date"])

    return df.sort_values("date")


def get_latest_health_note(health_notes_df):
    df = prepare_health_notes_for_charts(health_notes_df)

    if df.empty:
        return None

    return df.sort_values("date", ascending=False).iloc[0].to_dict()


def recent_health_notes_text(health_notes_df, limit=5):
    df = prepare_health_notes_for_charts(health_notes_df)

    if df.empty:
        return ""

    df = df.sort_values("date", ascending=False).head(limit)

    lines = []

    for _, row in df.iterrows():
        note_date = row.get("Date", "")
        pain = row.get("Pain 0-10", "")
        brain_fog = row.get("Brain fog 0-10", "")
        fatigue = row.get("Fatigue 0-10", "")
        mood = row.get("Mood", "")
        sleep_quality = row.get("Sleep quality", "")
        notes = row.get("Symptoms / Notes", "")
        questions = row.get("Questions for clinician", "")

        line = f"{note_date}:"

        details = []

        if not pd.isna(pain):
            details.append(f"pain {pain:.0f}/10")

        if not pd.isna(brain_fog):
            details.append(f"brain fog {brain_fog:.0f}/10")

        if not pd.isna(fatigue):
            details.append(f"fatigue {fatigue:.0f}/10")

        if str(mood).strip():
            details.append(f"mood: {mood}")

        if str(sleep_quality).strip():
            details.append(f"sleep quality: {sleep_quality}")

        if details:
            line += " " + ", ".join(details) + "."

        if str(notes).strip():
            line += f" Notes: {notes}"

        if str(questions).strip():
            line += f" Questions: {questions}"

        lines.append(line)

    return "\n".join(lines)


def symptom_summary_text(health_notes_df):
    df = prepare_health_notes_for_charts(health_notes_df)

    if df.empty:
        return "No symptom notes have been recorded yet."

    pain_avg = df["Pain 0-10"].mean()
    brain_avg = df["Brain fog 0-10"].mean()
    fatigue_avg = df["Fatigue 0-10"].mean()

    note_days = df["date"].nunique()
    latest = df.sort_values("date", ascending=False).iloc[0]

    lines = [
        f"Symptom notes have been recorded on {note_days} day(s).",
    ]

    if not pd.isna(pain_avg):
        lines.append(f"Average pain score: {pain_avg:.1f}/10.")

    if not pd.isna(brain_avg):
        lines.append(f"Average brain fog score: {brain_avg:.1f}/10.")

    if not pd.isna(fatigue_avg):
        lines.append(f"Average fatigue score: {fatigue_avg:.1f}/10.")

    latest_notes = str(latest.get("Symptoms / Notes", "") or "").strip()
    latest_questions = str(latest.get("Questions for clinician", "") or "").strip()

    if latest_notes:
        lines.append(f"Latest symptom note: {latest_notes}")

    if latest_questions:
        lines.append(f"Latest question for clinician: {latest_questions}")

    return " ".join(lines)


# ============================================================
# Summary builders
# ============================================================

def build_today_yesterday_3days(sleep_df, activity_df, food_daily_df, weight_df):
    today = today_date()
    yesterday = today - timedelta(days=1)
    three_start = today - timedelta(days=2)

    periods = [
        ("Today", today, today),
        ("Yesterday", yesterday, yesterday),
        ("Last 3 Days Avg", three_start, today),
    ]

    rows = []

    for label, start, end in periods:
        sleep_range = filter_by_date(sleep_df, start, end)
        activity_range = filter_by_date(activity_df, start, end)
        food_range = filter_by_date(food_daily_df, start, end)
        weight_range = filter_by_date(weight_df, start, end)

        sleep_avg = None
        steps_avg = None
        cal_avg = None
        protein_avg = None
        latest_weight = None

        if not sleep_range.empty and "sleep_hours" in sleep_range.columns:
            sleep_avg = sleep_range["sleep_hours"].mean()

        if not activity_range.empty and "steps" in activity_range.columns:
            steps_avg = activity_range["steps"].mean()

        if not food_range.empty and "calories" in food_range.columns:
            cal_avg = food_range["calories"].mean()

        if not food_range.empty and "protein_g" in food_range.columns:
            protein_avg = food_range["protein_g"].mean()

        if not weight_range.empty and "weight_kg" in weight_range.columns:
            latest_weight = weight_range.sort_values("date").iloc[-1]["weight_kg"]

        rows.append(
            {
                "Period": label,
                "Sleep": human_duration_short_from_hours(sleep_avg) if sleep_avg is not None and not pd.isna(sleep_avg) else "No data",
                "Steps": f"{steps_avg:,.0f}" if steps_avg is not None and not pd.isna(steps_avg) else "No data",
                "Calories": f"{cal_avg:,.0f}" if cal_avg is not None and not pd.isna(cal_avg) else "Not logged",
                "Protein": f"{protein_avg:.0f}g" if protein_avg is not None and not pd.isna(protein_avg) else "Not logged",
                "Weight": kg_to_st_lb(latest_weight) if latest_weight is not None and not pd.isna(latest_weight) else "No data",
            }
        )

    return pd.DataFrame(rows)


def build_hospital_summary(
    start_date,
    end_date,
    goals,
    sleep_range,
    activity_range,
    weight_range,
    food_daily_range,
    sleep_change,
    steps_change,
    weight_change_lb,
    protein_change,
    health_notes_df,
):
    days = (end_date - start_date).days + 1

    sleep_avg = None
    steps_avg = None
    calories_avg = None
    protein_avg = None
    carbs_avg = None
    fat_avg = None
    sugar_avg = None

    food_logged_days = food_daily_range["date"].nunique() if not food_daily_range.empty else 0

    if not sleep_range.empty and "sleep_hours" in sleep_range.columns:
        sleep_avg = sleep_range["sleep_hours"].mean()

    if not activity_range.empty and "steps" in activity_range.columns:
        steps_avg = activity_range["steps"].mean()

    if not food_daily_range.empty and "calories" in food_daily_range.columns:
        calories_avg = food_daily_range["calories"].mean()

    if not food_daily_range.empty and "protein_g" in food_daily_range.columns:
        protein_avg = food_daily_range["protein_g"].mean()

    if not food_daily_range.empty and "carbs_g" in food_daily_range.columns:
        carbs_avg = food_daily_range["carbs_g"].mean()

    if not food_daily_range.empty and "fat_g" in food_daily_range.columns:
        fat_avg = food_daily_range["fat_g"].mean()

    if not food_daily_range.empty and "sugar_g" in food_daily_range.columns:
        sugar_avg = food_daily_range["sugar_g"].mean()

    weight_start_text = "No data"
    weight_end_text = "No data"
    weight_change_text = "No data"

    if not weight_range.empty and "weight_kg" in weight_range.columns:
        w = weight_range.sort_values("date")
        start_weight = w.iloc[0]["weight_kg"]
        end_weight = w.iloc[-1]["weight_kg"]

        weight_start_text = kg_to_st_lb(start_weight)
        weight_end_text = kg_to_st_lb(end_weight)

        if weight_change_lb is not None:
            if abs(weight_change_lb) < 0.1:
                weight_change_text = "no real change"
            elif weight_change_lb < 0:
                weight_change_text = f"down {abs(weight_change_lb):.1f}lb ({pounds_to_st_lb_change(weight_change_lb)})"
            else:
                weight_change_text = f"up {weight_change_lb:.1f}lb ({pounds_to_st_lb_change(weight_change_lb)})"

    sleep_sentence = "Average sleep data was not available."

    if sleep_avg is not None and not pd.isna(sleep_avg):
        diff = goals["sleep_hours"] - sleep_avg

        if diff > 0:
            sleep_sentence = (
                f"My average sleep was {human_duration_from_hours(sleep_avg)}, "
                f"which is {human_duration_from_hours(diff)} under my "
                f"{human_duration_from_hours(goals['sleep_hours'])} goal."
            )
        else:
            sleep_sentence = (
                f"My average sleep was {human_duration_from_hours(sleep_avg)}, "
                f"which met or exceeded my sleep goal."
            )

        if sleep_change is not None:
            sleep_sentence += f" Compared with the earlier part of the period, sleep changed by {human_duration_short_from_hours(abs(sleep_change))} {'higher' if sleep_change > 0 else 'lower' if sleep_change < 0 else 'with no real change'}."

    steps_sentence = "Average step data was not available."

    if steps_avg is not None and not pd.isna(steps_avg):
        if steps_avg >= goals["steps"]:
            steps_sentence = (
                f"My average daily steps were {steps_avg:,.0f}, "
                f"which met my target of {goals['steps']:,.0f} steps."
            )
        else:
            steps_sentence = (
                f"My average daily steps were {steps_avg:,.0f}, "
                f"which is {goals['steps'] - steps_avg:,.0f} steps below my "
                f"target of {goals['steps']:,.0f}."
            )

        if steps_change is not None:
            steps_sentence += f" Compared with the earlier part of the period, average steps changed by {steps_change:+,.0f} steps."

    food_sentence = "Food data was not available for this period."

    if calories_avg is not None and not pd.isna(calories_avg):
        food_sentence = (
            f"My food data was logged on {food_logged_days} day(s) in this selected range. "
            f"Across those logged days, my average daily intake was around {calories_avg:,.0f} calories, "
            f"with protein averaging {protein_avg:.0f}g, carbs {carbs_avg:.0f}g, "
            f"fat {fat_avg:.0f}g and sugar {sugar_avg:.0f}g per day."
        )

        if protein_change is not None:
            food_sentence += f" Protein changed by {protein_change:+.0f}g compared with the earlier part of the period."

    weight_sentence = (
        f"My weight changed from {weight_start_text} to {weight_end_text}, "
        f"{weight_change_text}."
    )

    symptoms_sentence = symptom_summary_text(health_notes_df)
    recent_notes = recent_health_notes_text(health_notes_df, limit=5)

    notes_section = ""

    if recent_notes.strip():
        notes_section = (
            "\n\nRecent symptom notes:\n"
            f"{recent_notes}"
        )

    summary = (
        f"Health Overview, last {days} days\n"
        f"Date range: {start_date.strftime('%d %B %Y')} to {end_date.strftime('%d %B %Y')}\n\n"
        f"{sleep_sentence}\n"
        f"{steps_sentence}\n"
        f"{weight_sentence}\n"
        f"{food_sentence}\n"
        f"{symptoms_sentence}"
        f"{notes_section}\n\n"
        f"Overall, this gives a useful snapshot of my recent sleep, activity, weight, nutrition and symptom trends for discussion with the clinical team."
    )

    return summary


# ============================================================
# OAuth callback handling
# ============================================================

handle_withings_callback()


# ============================================================
# Sidebar controls
# ============================================================

st.title(APP_TITLE)
st.caption("Daily health dashboard showing today, recent history, sleep, steps, food, water and weight.")

with st.sidebar:
    if st.button("Lock dashboard on this device", use_container_width=True):
        st.session_state["dashboard_unlocked"] = False
        st.info("Dashboard locked on this device.")
        remember_cookie_clear_script()
        st.stop()

    st.header("History Range")

    history_range_options = {
        "3 days": 3,
        "7 days": 7,
        "14 days": 14,
        "30 days": 30,
        "60 days": 60,
        "90 days": 90,
    }

    history_range_label = st.radio(
        "Show history for",
        list(history_range_options.keys()),
        index=1,
        horizontal=False,
        key="history_range_radio",
    )

    history_days = history_range_options[history_range_label]
    history_start, history_end = date_range_from_days(history_days)

    today_start, today_end = today_date(), today_date()

    st.caption(f"History: {dashboard_date_label(history_start)} to {dashboard_date_label(history_end)}")

    st.divider()
    st.header("Withings")

    if WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET:
        auth_url = build_withings_auth_url()
        st.link_button("Connect / Reconnect Withings", auth_url, use_container_width=True)

        if st.button("Clear Withings token file", use_container_width=True):
            delete_tokens()
            st.cache_data.clear()
            st.success("Withings local token file cleared. If using Streamlit Secrets, the secret backup has not been changed.")

        current_tokens_for_backup = load_tokens()

        if current_tokens_for_backup and current_tokens_for_backup.get("refresh_token"):
            with st.expander("Cloud token backup"):
                st.caption(
                    "For Streamlit Cloud, copy this into App settings → Secrets after a successful Withings connection. "
                    "This helps the app reconnect after a cloud restart. Treat it like a password."
                )
                token_backup_text = (
                    'WITHINGS_TOKENS_JSON = """\n'
                    + json.dumps(current_tokens_for_backup, indent=2)
                    + '\n"""'
                )
                st.text_area(
                    "Copy this whole block into Streamlit Secrets",
                    token_backup_text,
                    height=240,
                    key="withings_token_backup_text",
                )
    else:
        st.warning("Add WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET to your .env file locally, or to Streamlit Secrets in the cloud.")

    st.divider()
    st.header("Google Drive Backup")

    if not GOOGLE_DRIVE_LIBS_AVAILABLE:
        st.warning("Google Drive packages are not installed.")
    else:
        drive_service, drive_error = get_google_drive_service()

        if drive_service is not None:
            st.success("Google Drive is connected.")
        else:
            st.info(drive_error or "Google Drive is not connected yet.")

        if st.button("Connect Google Drive", use_container_width=True):
            ok, message = connect_google_drive_locally()

            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

        if st.button("Back up Withings tokens to Google Drive now", use_container_width=True):
            tokens_for_drive_backup = load_tokens()

            if tokens_for_drive_backup and tokens_for_drive_backup.get("refresh_token"):
                ok, message = backup_withings_tokens_to_google_drive(tokens_for_drive_backup)

                if ok:
                    st.success(message)
                else:
                    st.error(message)
            else:
                st.warning("No Withings token with refresh token found yet.")

        if st.button("Restore Withings tokens from Google Drive", use_container_width=True):
            restored_tokens, restore_message = restore_withings_tokens_from_google_drive()

            if restored_tokens:
                st.success(restore_message)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(restore_message)

        google_token_backup = google_drive_token_backup_text()

        if google_token_backup:
            with st.expander("Google Drive token backup for Streamlit Secrets"):
                st.caption(
                    "Copy this into Streamlit Cloud Secrets if you want the cloud app to access Google Drive after restarts. "
                    "Treat it like a password."
                )
                st.text_area(
                    "Copy this whole block into Streamlit Secrets",
                    google_token_backup,
                    height=240,
                    key="google_drive_token_backup_text",
                )

    st.divider()
    st.header("Food Data")

    uploaded_food_files = st.file_uploader(
        "Upload MyNetDiary export",
        type=["xls", "xlsx"],
        accept_multiple_files=True,
        help="Upload files such as MyNetDiary_Year_2026.xls. Uploaded files are saved to Google Drive if Google Drive is connected.",
        key="food_file_uploader",
    )

    if uploaded_food_files:
        st.success(f"{len(uploaded_food_files)} food file(s) uploaded for this session.")
        for uploaded_file in uploaded_food_files:
            st.caption(uploaded_file.name)
    else:
        food_drive_files, food_drive_error = list_google_drive_food_files()

        if food_drive_files:
            st.success(f"{len(food_drive_files)} saved food file(s) found in Google Drive.")
            with st.expander("Saved MyNetDiary files"):
                for item in food_drive_files:
                    st.write(original_food_filename_from_drive_name(item.get("name", "")))
        elif food_drive_error:
            st.caption(f"Google Drive food file check: {food_drive_error}")
        else:
            st.caption("No food file uploaded yet and no saved food file found in Google Drive.")


# ============================================================
# New dashboard helpers
# ============================================================

def fmt_number(value, decimals=0, suffix=""):
    if value is None or pd.isna(value):
        return "No data"

    if decimals == 0:
        return f"{float(value):,.0f}{suffix}"

    return f"{float(value):,.{decimals}f}{suffix}"


def fmt_water(value):
    if value is None or pd.isna(value) or float(value) <= 0:
        return "No data"

    return fmt_number(value, suffix=" ml")


def dashboard_date_label(value):
    try:
        return pd.to_datetime(value).strftime("%a %d-%m-%y")
    except Exception:
        return str(value or "")


def dashboard_date_range_label(start_value, end_value):
    return f"{dashboard_date_label(start_value)} to {dashboard_date_label(end_value)}"


def infer_fluid_ml_from_text(*values):
    text = " ".join([str(v) for v in values if v is not None and not pd.isna(v)]).lower()

    if not any(word in text for word in ["water", "fluid", "fluids", "drink", "drinks", "ml", "litre", "liter"]):
        return 0.0

    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:ml|millilitre|millilitres|milliliter|milliliters)\b",
        r"(\d+(?:\.\d+)?)\s*(?:l|litre|litres|liter|liters)\b",
    ]

    ml_total = 0.0

    for match in re.finditer(patterns[0], text):
        ml_total += safe_float(match.group(1), 0)

    for match in re.finditer(patterns[1], text):
        ml_total += safe_float(match.group(1), 0) * 1000

    return ml_total


def clean_food_dataframe(food_table):
    if food_table is None or food_table.empty:
        return pd.DataFrame()

    df = food_table.copy()

    for col in ["meal", "food"]:
        if col not in df.columns:
            df[col] = ""

        df[col] = df[col].fillna("").astype(str).str.strip()

    meal_lower = df["meal"].str.lower()
    food_lower = df["food"].str.lower()

    # Do not show or count medication rows in the dashboard food totals.
    medication_mask = meal_lower.eq("medication") | food_lower.eq("medication")
    df = df[~medication_mask].copy()

    if df.empty:
        return df

    meal_lower = df["meal"].str.lower()
    food_lower = df["food"].str.lower()

    missing_food_mask = food_lower.isin(["", "0", "0.0", "nan", "none", "unknown food"])
    supplement_mask = meal_lower.str.contains("supplement", na=False)
    df.loc[supplement_mask & missing_food_mask, "food"] = "Supplement"

    # If MyNetDiary exports water as a food row instead of a Water/Fluid column,
    # infer ml from text such as "Water 500 ml" or "Water 2 L".
    if "fluid_ml" not in df.columns:
        df["fluid_ml"] = 0

    df["fluid_ml"] = pd.to_numeric(df["fluid_ml"], errors="coerce").fillna(0)
    inferred_water = df.apply(lambda row: infer_fluid_ml_from_text(row.get("meal"), row.get("food")), axis=1)
    df["fluid_ml"] = df["fluid_ml"].where(df["fluid_ml"] > 0, inferred_water)

    return df


def latest_value_for_metric(df, value_col, start_date=None, end_date=None):
    if df is None or df.empty or value_col not in df.columns:
        return None

    temp = df.copy()

    if start_date is not None and end_date is not None and "date" in temp.columns:
        temp = filter_by_date(temp, start_date, end_date)

    if temp.empty:
        return None

    temp = temp.dropna(subset=[value_col])

    if temp.empty:
        return None

    return temp.sort_values("date").iloc[-1][value_col]


def sum_for_day(df, day, value_col):
    if df is None or df.empty or "date" not in df.columns or value_col not in df.columns:
        return None

    temp = filter_by_date(df, day, day)

    if temp.empty:
        return None

    return temp[value_col].sum()


def mean_for_range(df, value_col):
    if df is None or df.empty or value_col not in df.columns:
        return None

    temp = df.dropna(subset=[value_col])

    if temp.empty:
        return None

    return temp[value_col].mean()


def prepare_food_table(food_table):
    if food_table is None or food_table.empty:
        return pd.DataFrame()

    display = clean_food_dataframe(food_table)

    if display.empty:
        return pd.DataFrame()

    for col in ["meal", "food"]:
        if col in display.columns:
            display[col] = display[col].fillna("").astype(str).str.strip()

    if "date" in display.columns:
        display["date"] = display["date"].apply(dashboard_date_label)

    rename_map = {
        "date": "Date",
        "meal": "Meal",
        "food": "Food",
        "protein_g": "Protein",
        "calories": "Calories",
    }

    # Keep the food table simple: no carbs, fat, sugar or water columns.
    cols = [c for c in ["date", "meal", "food", "protein_g", "calories"] if c in display.columns]
    display = display[cols].rename(columns=rename_map)

    for col in ["Protein", "Calories"]:
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce").round(0)

    return display

def sleep_rows_to_hourly_minutes(sleep_table):
    """
    Withings summary gives one start/end window per sleep day.
    This converts that window into approximate minutes asleep in each hour of the day.
    """
    hours = pd.DataFrame({"hour": list(range(24)), "minutes_asleep": [0.0] * 24})

    if sleep_table is None or sleep_table.empty:
        return hours

    for _, row in sleep_table.iterrows():
        start_time = str(row.get("start_time", "") or "")
        end_time = str(row.get("end_time", "") or "")
        sleep_hours = safe_float(row.get("sleep_hours", 0), 0)

        if not start_time or not end_time or ":" not in start_time or ":" not in end_time or sleep_hours <= 0:
            continue

        try:
            start_h, start_m = [int(x) for x in start_time.split(":")[:2]]
            end_h, end_m = [int(x) for x in end_time.split(":")[:2]]
        except Exception:
            continue

        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m

        if end_min <= start_min:
            end_min += 24 * 60

        max_duration = max(0, min(end_min - start_min, int(round(sleep_hours * 60))))

        cursor = start_min
        remaining = max_duration

        while remaining > 0:
            hour_index = (cursor // 60) % 24
            next_hour = ((cursor // 60) + 1) * 60
            minutes_this_hour = min(remaining, next_hour - cursor)

            hours.loc[hours["hour"] == hour_index, "minutes_asleep"] += minutes_this_hour

            cursor += minutes_this_hour
            remaining -= minutes_this_hour

    hours["hour_label"] = hours["hour"].apply(lambda h: f"{h:02d}:00")
    hours["minutes_asleep"] = hours["minutes_asleep"].clip(lower=0, upper=60)

    return hours


def sleep_timeline_chart(sleep_table, title, chart_key):
    hourly = sleep_rows_to_hourly_minutes(sleep_table)

    if hourly["minutes_asleep"].sum() <= 0:
        st.info("No sleep timing data available for this chart.")
        return

    fig = px.bar(
        hourly,
        x="hour_label",
        y="minutes_asleep",
        title=title,
        labels={"hour_label": "Time of day", "minutes_asleep": "Minutes asleep"},
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=[f"{h:02d}:00" for h in range(0, 24, 4)],
        ticktext=[f"{h:02d}:00" for h in range(0, 24, 4)],
    )
    fig.update_yaxes(range=[0, 60])
    fig.update_layout(height=330, margin=dict(l=20, r=20, t=50, b=20))

    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def daily_sleep_timing_chart(sleep_table, title, chart_key):
    if sleep_table is None or sleep_table.empty:
        st.info("No sleep timing data available.")
        return

    rows = []

    for _, row in sleep_table.iterrows():
        day = row.get("date")
        start_time = str(row.get("start_time", "") or "")
        end_time = str(row.get("end_time", "") or "")

        if not day or not start_time or not end_time or ":" not in start_time or ":" not in end_time:
            continue

        try:
            start_h, start_m = [int(x) for x in start_time.split(":")[:2]]
            end_h, end_m = [int(x) for x in end_time.split(":")[:2]]
        except Exception:
            continue

        start_hour = start_h + (start_m / 60)
        end_hour = end_h + (end_m / 60)

        if end_hour <= start_hour:
            rows.append({"date": day, "start_hour": start_hour, "end_hour": 24})
            rows.append({"date": day, "start_hour": 0, "end_hour": end_hour})
        else:
            rows.append({"date": day, "start_hour": start_hour, "end_hour": end_hour})

    chart_df = pd.DataFrame(rows)

    if chart_df.empty:
        st.info("No sleep timing data available.")
        return

    chart_df["duration"] = chart_df["end_hour"] - chart_df["start_hour"]
    chart_df["date_label"] = pd.to_datetime(chart_df["date"]).dt.strftime("%a %d-%m-%y")

    fig = px.bar(
        chart_df,
        x="duration",
        y="date_label",
        base="start_hour",
        orientation="h",
        title=title,
        labels={"date_label": "Date", "duration": "Sleep window", "start_hour": "Hour"},
    )

    fig.update_xaxes(
        range=[0, 24],
        tickmode="array",
        tickvals=list(range(0, 25, 2)),
        ticktext=[f"{h:02d}:00" for h in range(0, 25, 2)],
    )
    fig.update_layout(height=max(330, 34 * len(chart_df["date_label"].unique())), margin=dict(l=20, r=20, t=50, b=20))

    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def daily_total_chart(df, value_col, title, chart_key, chart_type="bar"):
    if df is None or df.empty or value_col not in df.columns:
        st.info("No data available for this chart.")
        return

    chart_df = df.copy().sort_values("date")
    chart_df["date_label"] = pd.to_datetime(chart_df["date"]).dt.strftime("%a %d-%m-%y")

    if chart_type == "line":
        fig = px.line(chart_df, x="date_label", y=value_col, markers=True, title=title)
    else:
        fig = px.bar(chart_df, x="date_label", y=value_col, title=title)

    fig.update_layout(height=340, margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


# ============================================================
# Load data
# ============================================================

runtime_tokens, runtime_refresh_error = get_runtime_withings_tokens()
runtime_access_token = runtime_tokens.get("access_token", "") if runtime_tokens else ""

sleep_df, sleep_error = get_withings_sleep(history_start, history_end, runtime_access_token)
activity_df, activity_error = get_withings_activity(history_start, history_end, runtime_access_token)
weight_df, weight_error = get_withings_weight(history_start, history_end, runtime_access_token)

withings_errors = {
    "sleep": sleep_error,
    "activity": activity_error,
    "weight": weight_error,
}

food_df, food_files, food_parse_messages = load_food_data(uploaded_food_files)
food_df = clean_food_dataframe(food_df)
food_daily = food_daily_summary(food_df)

today_sleep = filter_by_date(sleep_df, today_start, today_end)
today_activity = filter_by_date(activity_df, today_start, today_end)
today_food = filter_by_date(food_df, today_start, today_end)
today_food_daily = filter_by_date(food_daily, today_start, today_end)
today_weight = filter_by_date(weight_df, today_start, today_end)

history_sleep = filter_by_date(sleep_df, history_start, history_end)
history_activity = filter_by_date(activity_df, history_start, history_end)
history_food = filter_by_date(food_df, history_start, history_end)
history_food_daily = filter_by_date(food_daily, history_start, history_end)
history_weight = filter_by_date(weight_df, history_start, history_end)

today_steps = sum_for_day(activity_df, today_start, "steps")
today_sleep_hours = sum_for_day(sleep_df, today_start, "sleep_hours")
today_calories = sum_for_day(food_daily, today_start, "calories")
today_protein = sum_for_day(food_daily, today_start, "protein_g")
today_carbs = sum_for_day(food_daily, today_start, "carbs_g")
today_fat = sum_for_day(food_daily, today_start, "fat_g")
today_water = sum_for_day(food_daily, today_start, "fluid_ml")
latest_weight_kg = latest_value_for_metric(weight_df, "weight_kg")

history_avg_steps = mean_for_range(history_activity, "steps")
history_avg_sleep = mean_for_range(history_sleep, "sleep_hours")
history_avg_calories = mean_for_range(history_food_daily, "calories")
history_avg_protein = mean_for_range(history_food_daily, "protein_g")
history_avg_carbs = mean_for_range(history_food_daily, "carbs_g")
history_avg_fat = mean_for_range(history_food_daily, "fat_g")
history_avg_water = mean_for_range(history_food_daily, "fluid_ml")

if latest_weight_kg is None:
    latest_weight_kg = latest_value_for_metric(weight_df, "weight_kg")


# ============================================================
# Tabs
# ============================================================

tabs = st.tabs(
    [
        "Today",
        f"History ({selected_range_label(history_days)})",
        "Sleep",
        "Steps",
        "Food",
        "Weight",
    ]
)


# ============================================================
# Today tab
# ============================================================

with tabs[0]:
    st.subheader("Summary of Today")

    st.caption(f"Today is {dashboard_date_label(today_start)}.")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric("Daily Steps", fmt_number(today_steps))

    with c2:
        st.metric("Sleep", human_duration_from_hours(today_sleep_hours) if today_sleep_hours is not None else "No data")

    with c3:
        st.metric("Calories", fmt_number(today_calories))

    with c4:
        st.metric("Water", fmt_water(today_water))

    with c5:
        st.metric("Weight", kg_to_st_lb(latest_weight_kg) if latest_weight_kg is not None else "No data")

    st.divider()

    left, right = st.columns(2)

    with left:
        st.markdown("### Sleep Today, Midnight to Midnight")
        sleep_timeline_chart(
            today_sleep,
            "24 Hour Sleep Timeline",
            chart_key="today_sleep_timeline",
        )

    with right:
        st.markdown("### Protein, Carbs and Fat Today")
        macro_pie_chart(
            today_protein,
            today_carbs,
            today_fat,
            chart_key="today_macro_pie",
        )

    st.divider()

    st.markdown("### Food Today")

    today_food_display = prepare_food_table(today_food)

    if today_food_display.empty:
        st.info("No food has been logged for today yet.")
    else:
        st.dataframe(
            today_food_display,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    with st.expander("Data status"):
        withings_status = get_withings_status(
            sleep_df=sleep_df,
            activity_df=activity_df,
            weight_df=weight_df,
            errors=withings_errors,
            runtime_refresh_error=runtime_refresh_error,
        )

        st.markdown("#### Withings status")
        st.dataframe(withings_status, use_container_width=True, hide_index=True)

        st.markdown("#### Food status")

        if food_df.empty:
            st.warning("No usable food data loaded.")

            if food_files:
                st.write("Food files found / uploaded:", ", ".join([os.path.basename(str(f)) for f in food_files]))

            if food_parse_messages:
                for message in food_parse_messages:
                    st.write(message)
        else:
            st.write("Food rows loaded:", len(food_df))
            st.write("Food date range:", food_df["date"].min(), "to", food_df["date"].max())
            st.write("Food days loaded:", food_df["date"].nunique())
            st.write("Food files used:", ", ".join([os.path.basename(str(f)) for f in food_files]))

            if food_parse_messages:
                for message in food_parse_messages:
                    st.write(message)


# ============================================================
# History tab
# ============================================================

with tabs[1]:
    st.subheader(f"Summary Last {selected_range_label(history_days)}")

    st.caption(dashboard_date_range_label(history_start, history_end) + ".")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric("Average Daily Steps", fmt_number(history_avg_steps))

    with c2:
        st.metric("Average Sleep", human_duration_from_hours(history_avg_sleep) if history_avg_sleep is not None else "No data")

    with c3:
        st.metric("Average Calories", fmt_number(history_avg_calories))

    with c4:
        st.metric("Average Water", fmt_water(history_avg_water))

    with c5:
        st.metric("Latest Weight", kg_to_st_lb(latest_weight_kg) if latest_weight_kg is not None else "No data")

    st.divider()

    st.markdown("### Trends")

    h1, h2 = st.columns(2)

    with h1:
        daily_total_chart(
            history_activity,
            "steps",
            f"Daily Steps Last {selected_range_label(history_days)}",
            "history_steps_line",
            chart_type="line",
        )

    with h2:
        daily_total_chart(
            history_sleep,
            "sleep_hours",
            f"Sleep Hours Last {selected_range_label(history_days)}",
            "history_sleep_bar",
            chart_type="bar",
        )

    h3, h4 = st.columns(2)

    with h3:
        daily_total_chart(
            history_food_daily,
            "calories",
            f"Calories Last {selected_range_label(history_days)}",
            "history_calories_line",
            chart_type="line",
        )

    with h4:
        macro_pie_chart(
            history_avg_protein,
            history_avg_carbs,
            history_avg_fat,
            chart_key="history_macro_pie",
        )

    st.divider()

    st.markdown("### Sleep Timing")
    daily_sleep_timing_chart(
        history_sleep,
        f"Sleep Timing Last {selected_range_label(history_days)}",
        "history_sleep_timing",
    )

    st.divider()

    st.markdown("### Weight Last Selected Days")

    if history_weight.empty:
        st.info("No weight data found for this range.")
    else:
        weight_chart = history_weight.copy()
        weight_chart["weight_lb"] = weight_chart["weight_kg"] * 2.2046226218
        daily_total_chart(
            weight_chart,
            "weight_lb",
            "Weight Trend, lb",
            "history_weight_line",
            chart_type="line",
        )

    st.divider()

    st.markdown("### Food Last Selected Days")

    history_food_display = prepare_food_table(history_food)

    if history_food_display.empty:
        st.info("No food data found for this range.")
    else:
        st.dataframe(
            history_food_display,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Sleep tab
# ============================================================

with tabs[2]:
    st.subheader(f"Sleep Breakdown ({selected_range_label(history_days)})")

    if history_sleep.empty:
        st.info("No sleep data found.")

        if sleep_error:
            st.warning(f"Sleep API message: {sleep_error}")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Average Sleep", human_duration_from_hours(history_avg_sleep))

        with col2:
            st.metric("Longest Sleep", human_duration_from_hours(history_sleep["sleep_hours"].max()))

        with col3:
            st.metric("Shortest Sleep", human_duration_from_hours(history_sleep["sleep_hours"].min()))

        daily_total_chart(
            history_sleep,
            "sleep_hours",
            "Daily Sleep Hours",
            "sleep_breakdown_daily",
            chart_type="bar",
        )

        daily_sleep_timing_chart(
            history_sleep,
            "Sleep Timing by Day",
            "sleep_breakdown_timing",
        )

        st.markdown("### Sleep Table")

        display_sleep = history_sleep.copy().sort_values("date", ascending=False)
        display_sleep["Day"] = pd.to_datetime(display_sleep["date"]).dt.strftime("%a")
        display_sleep["date"] = display_sleep["date"].apply(dashboard_date_label)
        display_sleep["Sleep"] = display_sleep["sleep_hours"].apply(human_duration_short_from_hours)

        st.dataframe(
            display_sleep[["date", "Day", "Sleep", "start_time", "end_time"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Steps tab
# ============================================================

with tabs[3]:
    st.subheader(f"Daily Steps ({selected_range_label(history_days)})")

    if history_activity.empty:
        st.info("No step data found.")

        if activity_error:
            st.warning(f"Steps API message: {activity_error}")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Average Steps", fmt_number(history_avg_steps))

        with col2:
            st.metric("Best Day", fmt_number(history_activity["steps"].max()))

        with col3:
            st.metric("Lowest Day", fmt_number(history_activity["steps"].min()))

        daily_total_chart(
            history_activity,
            "steps",
            "Daily Steps",
            "steps_breakdown_line",
            chart_type="line",
        )

        display_steps = history_activity.copy().sort_values("date", ascending=False)
        display_steps["Day"] = pd.to_datetime(display_steps["date"]).dt.strftime("%a")
        display_steps["date"] = display_steps["date"].apply(dashboard_date_label)

        st.dataframe(
            display_steps[["date", "Day", "steps"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Food tab
# ============================================================

with tabs[4]:
    st.subheader(f"Food, Calories and Water ({selected_range_label(history_days)})")

    if food_df.empty:
        st.info(
            "No usable food data found yet. Upload a MyNetDiary export, or check that the saved file has Date, Food, Calories, Protein, Carbs and Fat columns."
        )

        if food_files:
            with st.expander("Food files found / uploaded"):
                for file in food_files:
                    st.write(os.path.basename(str(file)))

        if food_parse_messages:
            with st.expander("Food import messages"):
                for message in food_parse_messages:
                    st.write(message)
    elif history_food_daily.empty:
        st.info("Food files were found, but there is no food data in the selected date range.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.metric("Average Calories", fmt_number(history_avg_calories))

        with c2:
            st.metric("Average Protein", fmt_number(history_avg_protein, suffix="g"))

        with c3:
            st.metric("Average Carbs", fmt_number(history_avg_carbs, suffix="g"))

        with c4:
            st.metric("Average Fat", fmt_number(history_avg_fat, suffix="g"))

        with c5:
            st.metric("Average Water", fmt_water(history_avg_water))

        left, right = st.columns(2)

        with left:
            daily_total_chart(
                history_food_daily,
                "calories",
                "Daily Calories",
                "food_breakdown_calories",
                chart_type="bar",
            )

        with right:
            macro_pie_chart(
                history_avg_protein,
                history_avg_carbs,
                history_avg_fat,
                chart_key="food_breakdown_macro",
            )

        if "fluid_ml" in history_food_daily.columns and pd.to_numeric(history_food_daily["fluid_ml"], errors="coerce").fillna(0).sum() > 0:
            daily_total_chart(
                history_food_daily,
                "fluid_ml",
                "Daily Water / Fluid ml",
                "food_breakdown_water",
                chart_type="bar",
            )
        else:
            st.info("No water data found in the MyNetDiary export for this range.")

        st.divider()

        st.markdown("### Food Table")

        display_food = prepare_food_table(history_food.sort_values("date", ascending=False))

        st.dataframe(
            display_food,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Weight tab
# ============================================================

with tabs[5]:
    st.subheader(f"Weight ({selected_range_label(history_days)})")

    if history_weight.empty:
        st.info("No weight data found.")

        if weight_error:
            st.warning(f"Weight API message: {weight_error}")
    else:
        w = history_weight.sort_values("date")

        start_weight = w.iloc[0]["weight_kg"]
        end_weight = w.iloc[-1]["weight_kg"]
        diff_kg = end_weight - start_weight
        diff_lb = diff_kg * 2.2046226218

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Start Weight", kg_to_st_lb(start_weight))

        with col2:
            st.metric("Latest Weight", kg_to_st_lb(end_weight))

        with col3:
            st.metric("Change", pounds_to_st_lb_change(diff_lb), delta=f"{diff_lb:+.1f}lb")

        weight_chart = history_weight.copy()
        weight_chart["weight_lb"] = weight_chart["weight_kg"] * 2.2046226218

        daily_total_chart(
            weight_chart,
            "weight_lb",
            "Weight Trend, lb",
            "weight_breakdown_line",
            chart_type="line",
        )

        display_weight = history_weight.copy().sort_values("date", ascending=False)
        display_weight["Day"] = pd.to_datetime(display_weight["date"]).dt.strftime("%a")
        display_weight["date"] = display_weight["date"].apply(dashboard_date_label)
        display_weight["kg"] = display_weight["weight_kg"].round(2)
        display_weight["stone_lb"] = display_weight["weight_kg"].apply(kg_to_st_lb)

        st.markdown("### Weight Table")

        st.dataframe(
            display_weight[["date", "Day", "stone_lb", "kg"]],
            use_container_width=True,
            hide_index=True,
        )

