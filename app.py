import os
import json
import glob
from datetime import datetime, date, timedelta
from urllib.parse import urlencode
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
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
GOALS_FILE = os.path.join(BASE_DIR, "dashboard_goals.json")
MEDICATIONS_FILE = os.path.join(BASE_DIR, "medications.csv")
APPOINTMENTS_FILE = os.path.join(BASE_DIR, "appointments.csv")
HEALTH_NOTES_FILE = os.path.join(BASE_DIR, "health_notes.csv")
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


# ============================================================
# Password protection
# ============================================================

def check_dashboard_login():
    """
    Stop the dashboard loading until the correct username and password are entered.
    Username and password are read from Streamlit Secrets / environment / .env as
    APP_USERNAME and APP_PASSWORD.
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

    st.title(APP_TITLE)
    st.caption("Private dashboard. Please enter your username and password to continue.")

    with st.form("dashboard_login_form"):
        entered_username = st.text_input("Username")
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock Dashboard")

    if submitted:
        username_ok = entered_username.strip().lower() == str(APP_USERNAME).strip().lower()
        password_ok = entered_password == str(APP_PASSWORD)

        if username_ok and password_ok:
            st.session_state["dashboard_unlocked"] = True
            st.rerun()
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
    values = [safe_float(protein), safe_float(carbs), safe_float(fat)]
    labels = ["Protein", "Carbs", "Fat"]

    if sum(values) <= 0:
        st.info("No macro data available.")
        return

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.35,
                pull=[0.12, 0, 0],
                marker=dict(
                    colors=[
                        "#D9B3FF",
                        "#CDECCF",
                        "#B8860B",
                    ]
                ),
            )
        ]
    )

    fig.update_layout(
        title="Macro Split, Protein Highlighted",
        height=380,
        margin=dict(l=20, r=20, t=50, b=20),
    )

    if chart_key is None:
        chart_key = "macro_pie_chart"

    st.plotly_chart(fig, use_container_width=True, key=chart_key)


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
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return load_tokens_from_secrets()


def save_tokens(tokens):
    # Store in the app session so the latest token can be used immediately.
    try:
        st.session_state["latest_withings_tokens"] = tokens
    except Exception:
        pass

    # Also write a local token file. On Streamlit Cloud this file may disappear
    # after restart, so WITHINGS_TOKENS_JSON in Secrets is the long-term backup.
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
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
                fluid_col = find_col(df.columns, ["Water", "Fluid", "Fluids", "Water ml", "Fluid ml", "Fluids ml"])

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
    files = sorted(list(set(files)))

    for path in files:
        sources.append(
            {
                "name": os.path.basename(path),
                "path": path,
                "bytes": None,
            }
        )

    food_df, files_seen, parse_messages = parse_mynetdiary_sources(sources)

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

    if uploaded_food_files:
        for uploaded_file in uploaded_food_files:
            uploaded_payloads.append(
                {
                    "name": uploaded_file.name,
                    "bytes": uploaded_file.getvalue(),
                }
            )

    if uploaded_payloads:
        return load_food_data_from_uploads(uploaded_payloads)

    return load_food_data_from_local_files()


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
    if os.path.exists(MEDICATIONS_FILE):
        try:
            return pd.read_csv(MEDICATIONS_FILE)
        except Exception:
            pass

    df = pd.DataFrame(DEFAULT_MEDICATIONS)
    df.to_csv(MEDICATIONS_FILE, index=False)

    return df


def save_medications(df):
    df.to_csv(MEDICATIONS_FILE, index=False)


def load_appointments():
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

    return df


def save_appointments(df):
    df.to_csv(APPOINTMENTS_FILE, index=False)


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
    if os.path.exists(HEALTH_NOTES_FILE):
        try:
            df = pd.read_csv(HEALTH_NOTES_FILE)
            df = clean_health_notes_df(df)
            df.to_csv(HEALTH_NOTES_FILE, index=False)
            return df
        except Exception:
            pass

    df = empty_health_notes_df()
    df.to_csv(HEALTH_NOTES_FILE, index=False)

    return df


def save_health_notes(df):
    clean_df = clean_health_notes_df(df)
    clean_df.to_csv(HEALTH_NOTES_FILE, index=False)


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
st.caption("Sleep, steps, weight, food, hospital summaries, medication, appointments and health notes.")

goals = load_json_file(GOALS_FILE, DEFAULT_GOALS)

with st.sidebar:
    st.header("Dashboard Range")

    main_range_options = {
        "1 day": 1,
        "2 days": 2,
        "3 days": 3,
        "7 days": 7,
        "14 days": 14,
        "21 days": 21,
        "28 days": 28,
        "6 weeks": 42,
        "2 months": 60,
    }

    weight_range_options = {
        "2 weeks": 14,
        "3 weeks": 21,
        "4 weeks": 28,
        "6 weeks": 42,
        "2 months": 60,
        "3 months": 90,
    }

    main_range_label = st.radio(
        "Main range",
        list(main_range_options.keys()),
        index=2,
        horizontal=False,
        key="main_range_radio",
    )

    weight_range_label = st.radio(
        "Weight range",
        list(weight_range_options.keys()),
        index=0,
        horizontal=False,
        key="weight_range_radio",
    )

    main_days = main_range_options[main_range_label]
    weight_days = weight_range_options[weight_range_label]

    main_start, main_end = date_range_from_days(main_days)
    weight_start, weight_end = date_range_from_days(weight_days)

    st.divider()
    st.caption(f"Main range: {main_start.strftime('%d %b %Y')} to {main_end.strftime('%d %b %Y')}")
    st.caption(f"Weight range: {weight_start.strftime('%d %b %Y')} to {weight_end.strftime('%d %b %Y')}")

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
                    "WITHINGS_TOKENS_JSON = '''\n"
                    + json.dumps(current_tokens_for_backup, indent=2)
                    + "\n'''"
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
    st.header("Food Data")

    uploaded_food_files = st.file_uploader(
        "Upload MyNetDiary export",
        type=["xls", "xlsx"],
        accept_multiple_files=True,
        help="Upload files such as MyNetDiary_Year_2026.xls. In Streamlit Cloud this keeps food data private in your current session.",
        key="food_file_uploader",
    )

    if uploaded_food_files:
        st.success(f"{len(uploaded_food_files)} food file(s) uploaded for this session.")
        for uploaded_file in uploaded_food_files:
            st.caption(uploaded_file.name)
    else:
        st.caption("No food file uploaded yet.")


# ============================================================
# Load data
# ============================================================

runtime_tokens, runtime_refresh_error = get_runtime_withings_tokens()
runtime_access_token = runtime_tokens.get("access_token", "") if runtime_tokens else ""

sleep_df, sleep_error = get_withings_sleep(main_start, main_end, runtime_access_token)
activity_df, activity_error = get_withings_activity(main_start, main_end, runtime_access_token)
weight_df, weight_error = get_withings_weight(weight_start, weight_end, runtime_access_token)

withings_errors = {
    "sleep": sleep_error,
    "activity": activity_error,
    "weight": weight_error,
}

food_df, food_files, food_parse_messages = load_food_data(uploaded_food_files)
food_range = filter_by_date(food_df, main_start, main_end)
food_daily = food_daily_summary(food_df)
food_daily_range = filter_by_date(food_daily, main_start, main_end)

sleep_range = filter_by_date(sleep_df, main_start, main_end)
activity_range = filter_by_date(activity_df, main_start, main_end)
weight_range = filter_by_date(weight_df, weight_start, weight_end)

health_notes_df = load_health_notes()
health_notes_chart_df = prepare_health_notes_for_charts(health_notes_df)
latest_health_note = get_latest_health_note(health_notes_df)

today_table = build_today_yesterday_3days(
    sleep_df=sleep_df,
    activity_df=activity_df,
    food_daily_df=food_daily,
    weight_df=weight_df,
)


# ============================================================
# Summary values and trends
# ============================================================

avg_sleep = None
avg_steps = None
avg_calories = None
avg_protein = None
avg_carbs = None
avg_fat = None
latest_weight_kg = None
weight_change_lb = None

if not sleep_range.empty and "sleep_hours" in sleep_range.columns:
    avg_sleep = sleep_range["sleep_hours"].mean()

if not activity_range.empty and "steps" in activity_range.columns:
    avg_steps = activity_range["steps"].mean()

if not food_daily_range.empty and "calories" in food_daily_range.columns:
    avg_calories = food_daily_range["calories"].mean()

if not food_daily_range.empty and "protein_g" in food_daily_range.columns:
    avg_protein = food_daily_range["protein_g"].mean()

if not food_daily_range.empty and "carbs_g" in food_daily_range.columns:
    avg_carbs = food_daily_range["carbs_g"].mean()

if not food_daily_range.empty and "fat_g" in food_daily_range.columns:
    avg_fat = food_daily_range["fat_g"].mean()

if not weight_range.empty and "weight_kg" in weight_range.columns:
    w_sorted = weight_range.sort_values("date")
    latest_weight_kg = w_sorted.iloc[-1]["weight_kg"]

    if len(w_sorted) >= 2:
        start_weight_kg = w_sorted.iloc[0]["weight_kg"]
        end_weight_kg = w_sorted.iloc[-1]["weight_kg"]
        weight_change_lb = (end_weight_kg - start_weight_kg) * 2.2046226218

sleep_first, sleep_second, sleep_change = compare_first_last_half(sleep_range, "sleep_hours")
steps_first, steps_second, steps_change = compare_first_last_half(activity_range, "steps")
calorie_first, calorie_second, calorie_change = compare_first_last_half(food_daily_range, "calories")
protein_first, protein_second, protein_change = compare_first_last_half(food_daily_range, "protein_g")

sleep_status, sleep_detail = status_badge(
    avg_sleep,
    goals["sleep_hours"],
    higher_is_better=True,
    amber_margin=0.10,
)

steps_status, steps_detail = status_badge(
    avg_steps,
    goals["steps"],
    higher_is_better=True,
    amber_margin=0.10,
)

protein_status, protein_detail = status_badge(
    avg_protein,
    goals["protein_g"],
    higher_is_better=True,
    amber_margin=0.10,
)

target_weight_kg = stones_to_kg(goals["target_weight_stones"])

weight_status, weight_detail = status_badge(
    latest_weight_kg,
    target_weight_kg,
    higher_is_better=False,
    amber_margin=0.05,
)


# ============================================================
# Tabs
# ============================================================

tabs = st.tabs(
    [
        f"Summary ({selected_range_label(main_days)})",
        "Sleep",
        "Steps",
        "Weight",
        "Food",
        "Hospital",
        "Health Notes",
        "Medication",
        "Appointments",
        "Goals",
    ]
)


# ============================================================
# Summary tab
# ============================================================

with tabs[0]:
    st.subheader(f"Summary ({selected_range_label(main_days)})")

    st.caption("Quick overview of sleep, steps, weight, nutrition and symptoms for the selected range.")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        sleep_delta = f"{sleep_change:+.2f} hrs" if sleep_change is not None else None
        metric_card(
            "Average Sleep",
            human_duration_short_from_hours(avg_sleep) if avg_sleep is not None and not pd.isna(avg_sleep) else "No data",
            delta=sleep_delta,
        )
        small_warning("Status", sleep_status)

    with col2:
        steps_delta = f"{steps_change:+,.0f}" if steps_change is not None else None
        metric_card(
            "Average Steps",
            f"{avg_steps:,.0f}" if avg_steps is not None and not pd.isna(avg_steps) else "No data",
            delta=steps_delta,
        )
        small_warning("Status", steps_status)

    with col3:
        weight_delta = f"{weight_change_lb:+.1f}lb" if weight_change_lb is not None else None
        metric_card(
            "Current Weight",
            kg_to_st_lb(latest_weight_kg) if latest_weight_kg is not None else "No data",
            delta=weight_delta,
        )
        small_warning("Status", weight_status)

    with col4:
        protein_delta = f"{protein_change:+.0f}g" if protein_change is not None else None
        metric_card(
            "Average Protein",
            f"{avg_protein:.0f}g" if avg_protein is not None and not pd.isna(avg_protein) else "No data",
            delta=protein_delta,
        )
        small_warning("Status", protein_status)

    st.divider()

    st.markdown("### Recent Trends")

    t1, t2, t3, t4 = st.columns(4)

    with t1:
        if sleep_change is None:
            show_trend_card("Sleep trend", "No data", "Not enough sleep data to compare.", sleep_status)
        else:
            show_trend_card(
                "Sleep trend",
                f"{trend_arrow(sleep_change)} {human_duration_short_from_hours(abs(sleep_change))}",
                "Change between earlier and later part of selected range.",
                sleep_status,
            )

    with t2:
        if steps_change is None:
            show_trend_card("Steps trend", "No data", "Not enough step data to compare.", steps_status)
        else:
            show_trend_card(
                "Steps trend",
                f"{trend_arrow(steps_change)} {steps_change:+,.0f}",
                "Average step change across the selected range.",
                steps_status,
            )

    with t3:
        if weight_change_lb is None:
            show_trend_card("Weight trend", "No data", "Not enough weight data to compare.", weight_status)
        else:
            show_trend_card(
                "Weight trend",
                f"{trend_arrow(weight_change_lb, lower_is_better=True)} {pounds_to_st_lb_change(weight_change_lb)}",
                f"Total change over {selected_range_label(weight_days).lower()}.",
                weight_status,
            )

    with t4:
        if protein_change is None:
            show_trend_card("Protein trend", "No data", "Not enough food data to compare.", protein_status)
        else:
            show_trend_card(
                "Protein trend",
                f"{trend_arrow(protein_change)} {protein_change:+.0f}g",
                "Average protein change across logged food days.",
                protein_status,
            )

    st.divider()

    st.markdown("### Latest Health Note")

    if latest_health_note:
        h1, h2, h3, h4 = st.columns(4)

        with h1:
            pain_value = latest_health_note.get("Pain 0-10")
            st.metric("Pain", f"{pain_value:.0f}/10" if not pd.isna(pain_value) else "No data")

        with h2:
            brain_value = latest_health_note.get("Brain fog 0-10")
            st.metric("Brain Fog", f"{brain_value:.0f}/10" if not pd.isna(brain_value) else "No data")

        with h3:
            fatigue_value = latest_health_note.get("Fatigue 0-10")
            st.metric("Fatigue", f"{fatigue_value:.0f}/10" if not pd.isna(fatigue_value) else "No data")

        with h4:
            st.metric("Mood", str(latest_health_note.get("Mood", "") or "No data"))

        latest_note_text = str(latest_health_note.get("Symptoms / Notes", "") or "").strip()
        latest_question_text = str(latest_health_note.get("Questions for clinician", "") or "").strip()

        if latest_note_text:
            st.caption(f"Latest note: {latest_note_text}")

        if latest_question_text:
            st.caption(f"Question for clinician: {latest_question_text}")
    else:
        st.info("No health notes saved yet.")

    st.divider()

    st.markdown("### Today / Yesterday / Last 3 Days")
    st.dataframe(today_table, use_container_width=True, hide_index=True)

    st.divider()

    left, right = st.columns(2)

    with left:
        simple_bar_chart(
            sleep_range,
            "date",
            "sleep_hours",
            "Daily Sleep Hours",
            chart_key="summary_sleep_bar",
        )

    with right:
        simple_bar_chart(
            activity_range,
            "date",
            "steps",
            "Daily Steps",
            chart_key="summary_steps_bar",
        )

    st.divider()

    with st.expander("System / Data Status"):
        withings_status = get_withings_status(
            sleep_df=sleep_df,
            activity_df=activity_df,
            weight_df=weight_df,
            errors=withings_errors,
            runtime_refresh_error=runtime_refresh_error,
        )

        st.markdown("#### Withings status")
        st.dataframe(withings_status, use_container_width=True, hide_index=True)

        if not WITHINGS_CLIENT_ID or not WITHINGS_CLIENT_SECRET:
            st.warning("Missing Client ID or Client Secret in .env / Streamlit Secrets.")
        elif sleep_df.empty and activity_df.empty and weight_df.empty:
            st.warning("No Withings sleep, steps or weight data has loaded. Check the API errors above.")
        elif sleep_df.empty or activity_df.empty or weight_df.empty:
            st.info("Some Withings data is missing. Check the API errors above.")
        else:
            st.success("Withings data is loading.")

        st.markdown("#### Food status")

        if food_df.empty:
            st.warning("No usable food data loaded.")

            if food_files:
                st.write("Food files found / uploaded:", ", ".join([os.path.basename(str(f)) for f in food_files]))

            if food_parse_messages:
                with st.expander("Food import messages"):
                    for message in food_parse_messages:
                        st.write(message)
        else:
            st.write("Food rows loaded:", len(food_df))
            st.write("Food date range:", food_df["date"].min(), "to", food_df["date"].max())
            st.write("Food days loaded:", food_df["date"].nunique())
            st.write("Food files used:", ", ".join([os.path.basename(str(f)) for f in food_files]))

            if food_parse_messages:
                with st.expander("Food import messages"):
                    for message in food_parse_messages:
                        st.write(message)

        st.markdown("#### Health notes status")

        if health_notes_df.empty:
            st.warning("No health notes loaded.")
        else:
            st.write("Health note rows loaded:", len(health_notes_df))


# ============================================================
# Sleep tab
# ============================================================

with tabs[1]:
    st.subheader(f"Sleep ({selected_range_label(main_days)})")

    if sleep_range.empty:
        st.info("No sleep data found.")

        if sleep_error:
            st.warning(f"Sleep API message: {sleep_error}")
    else:
        col1, col2, col3 = st.columns(3)

        best_sleep = sleep_range["sleep_hours"].max()
        worst_sleep = sleep_range["sleep_hours"].min()
        days_under_goal = int((sleep_range["sleep_hours"] < goals["sleep_hours"]).sum())

        with col1:
            st.metric("Average Sleep", human_duration_from_hours(avg_sleep))

        with col2:
            st.metric("Best Sleep", human_duration_from_hours(best_sleep))

        with col3:
            st.metric("Days Under Goal", days_under_goal)

        if avg_sleep is not None and not pd.isna(avg_sleep):
            sleep_gap = goals["sleep_hours"] - avg_sleep

            if sleep_gap > 0:
                st.caption(
                    f"Average sleep is {human_duration_from_hours(sleep_gap)} under your "
                    f"{human_duration_from_hours(goals['sleep_hours'])} goal."
                )
            else:
                st.caption("Average sleep is meeting your goal.")

        simple_bar_chart(
            sleep_range,
            "date",
            "sleep_hours",
            "Daily Sleep",
            chart_key="sleep_tab_sleep_bar",
        )

        display_sleep = sleep_range.copy()
        display_sleep["Sleep"] = display_sleep["sleep_hours"].apply(human_duration_short_from_hours)
        display_sleep["Day"] = pd.to_datetime(display_sleep["date"]).dt.strftime("%a")
        display_sleep = display_sleep.sort_values("date", ascending=False)

        st.markdown("### Sleep Table")

        st.dataframe(
            display_sleep[["date", "Day", "Sleep", "start_time", "end_time"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Steps tab
# ============================================================

with tabs[2]:
    st.subheader(f"Steps ({selected_range_label(main_days)})")

    if activity_range.empty:
        st.info("No step data found.")

        if activity_error:
            st.warning(f"Steps API message: {activity_error}")
    else:
        col1, col2, col3 = st.columns(3)

        best_steps = activity_range["steps"].max()
        worst_steps = activity_range["steps"].min()
        days_above_goal = int((activity_range["steps"] >= goals["steps"]).sum())

        with col1:
            st.metric("Average Steps", f"{avg_steps:,.0f}")

        with col2:
            st.metric("Best Day", f"{best_steps:,.0f}")

        with col3:
            st.metric("Days On Target", days_above_goal)

        if avg_steps is not None and not pd.isna(avg_steps):
            step_gap = goals["steps"] - avg_steps

            if step_gap > 0:
                st.caption(f"Average steps are {step_gap:,.0f} below your {goals['steps']:,.0f} step goal.")
            else:
                st.caption("Average steps are meeting your goal.")

        simple_bar_chart(
            activity_range,
            "date",
            "steps",
            "Daily Steps",
            chart_key="steps_tab_steps_bar",
        )

        display_steps = activity_range.copy()
        display_steps["Day"] = pd.to_datetime(display_steps["date"]).dt.strftime("%a")
        display_steps = display_steps.sort_values("date", ascending=False)

        st.dataframe(
            display_steps[["date", "Day", "steps"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Weight tab
# ============================================================

with tabs[3]:
    st.subheader(f"Weight ({selected_range_label(weight_days)})")

    if weight_range.empty:
        st.info("No weight data found.")

        if weight_error:
            st.warning(f"Weight API message: {weight_error}")
    else:
        w = weight_range.sort_values("date")

        start_weight = w.iloc[0]["weight_kg"]
        end_weight = w.iloc[-1]["weight_kg"]

        diff_kg = end_weight - start_weight
        diff_lb = diff_kg * 2.2046226218

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Start Weight", kg_to_st_lb(start_weight))

        with col2:
            st.metric("Current Weight", kg_to_st_lb(end_weight))

        with col3:
            st.metric("Change", pounds_to_st_lb_change(diff_lb), delta=f"{diff_lb:+.1f}lb")

        with col4:
            st.metric("Target", f"{goals['target_weight_stones']:.1f} stone")

        target_kg = stones_to_kg(goals["target_weight_stones"])
        over_target_lb = (end_weight - target_kg) * 2.2046226218

        if over_target_lb > 0:
            st.caption(f"Current weight is {over_target_lb:.1f}lb above your target.")
        else:
            st.caption(f"Current weight is {abs(over_target_lb):.1f}lb below your target.")

        chart_weight = weight_range.copy()
        chart_weight["weight_lb"] = chart_weight["weight_kg"] * 2.2046226218

        simple_line_chart(
            chart_weight,
            "date",
            "weight_lb",
            "Weight Trend, lb",
            chart_key="weight_tab_weight_line",
        )

        display_weight = weight_range.copy()
        display_weight["Day"] = pd.to_datetime(display_weight["date"]).dt.strftime("%a")
        display_weight["kg"] = display_weight["weight_kg"].round(2)
        display_weight["stone_lb"] = display_weight["weight_kg"].apply(kg_to_st_lb)
        display_weight = display_weight.sort_values("date", ascending=False)

        st.markdown("### Weight Table")

        st.dataframe(
            display_weight[["date", "Day", "stone_lb", "kg"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Food tab
# ============================================================

with tabs[4]:
    st.subheader(f"Food ({selected_range_label(main_days)})")

    if food_df.empty:
        st.info(
            "No usable food data found yet. The file may be found, but the columns may not be readable. "
            "Try opening the MyNetDiary export and checking whether it has Date, Food, Calories, Protein, Carbs and Fat columns."
        )

        if food_files:
            with st.expander("Food files found / uploaded"):
                for file in food_files:
                    st.write(os.path.basename(str(file)))

        if food_parse_messages:
            with st.expander("Food import messages"):
                for message in food_parse_messages:
                    st.write(message)
    else:
        if food_files:
            with st.expander("Food files found / uploaded"):
                for file in food_files:
                    st.write(os.path.basename(str(file)))

        if food_parse_messages:
            with st.expander("Food import messages"):
                for message in food_parse_messages:
                    st.write(message)

        with st.expander("Food data debug"):
            food_logged_days = food_df["date"].nunique()
            selected_food_logged_days = food_range["date"].nunique() if not food_range.empty else 0

            st.write("Rows loaded:", len(food_df))
            st.write("Days with food logged:", food_logged_days)
            st.write("Days with food logged in selected range:", selected_food_logged_days)
            st.write("Date range loaded:", food_df["date"].min(), "to", food_df["date"].max())
            st.write("Columns loaded:", list(food_df.columns))

        if food_daily_range.empty:
            st.info("Food files were found, but there is no food data in the selected date range.")
        else:
            logged_days_in_range = food_daily_range["date"].nunique()

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Average Calories", f"{avg_calories:,.0f}")

            with col2:
                protein_delta = f"{protein_change:+.0f}g" if protein_change is not None else None
                st.metric("Average Protein", f"{avg_protein:.0f}g", delta=protein_delta)

            with col3:
                st.metric("Average Carbs", f"{avg_carbs:.0f}g")

            with col4:
                st.metric("Average Fat", f"{avg_fat:.0f}g")

            st.caption(
                f"Protein target: {goals['protein_g']}g per day. "
                f"Calorie budget: {goals['calories']} kcal per day. "
                f"Averages are based on {logged_days_in_range} logged food day(s) in this selected range."
            )

            left, right = st.columns(2)

            with left:
                simple_bar_chart(
                    food_daily_range,
                    "date",
                    "calories",
                    "Daily Calories",
                    chart_key="food_tab_calories_bar",
                )

            with right:
                macro_pie_chart(
                    avg_protein,
                    avg_carbs,
                    avg_fat,
                    chart_key="food_tab_macro_pie",
                )

            st.divider()

            st.markdown("### Typical Food Day From Selected Range")

            typical = build_typical_food_day(food_range)

            if not typical:
                st.info("Not enough food item detail available for a typical food day.")
            else:
                for meal, foods in typical.items():
                    if foods.empty:
                        continue

                    st.markdown(f"#### {meal}")

                    food_lines = []

                    for _, row in foods.iterrows():
                        food_name = str(row["food"])
                        avg_cals = safe_float(row["avg_calories"])
                        avg_pro = safe_float(row["avg_protein"])
                        seen = safe_int(row["times_seen"])

                        food_lines.append(
                            f"- {food_name}, seen {seen} times, approx {avg_cals:.0f} kcal, {avg_pro:.0f}g protein"
                        )

                    st.markdown("\n".join(food_lines))

            st.divider()

            st.markdown("### Food Table")

            display_food = food_range.copy()
            display_food = display_food.sort_values("date", ascending=False)

            st.dataframe(
                display_food[
                    [
                        "date",
                        "meal",
                        "food",
                        "calories",
                        "protein_g",
                        "carbs_g",
                        "fat_g",
                        "sugar_g",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# Hospital tab
# ============================================================

with tabs[5]:
    st.subheader("Hospital Summary")

    st.caption("A cleaner copy-and-paste overview for hospital, GP, pain clinic, dietitian or transplant review.")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Average Sleep",
            human_duration_short_from_hours(avg_sleep) if avg_sleep is not None and not pd.isna(avg_sleep) else "No data",
            delta=f"{sleep_change:+.2f} hrs" if sleep_change is not None else None,
        )
        st.caption(sleep_status)

    with col2:
        st.metric(
            "Average Steps",
            f"{avg_steps:,.0f}" if avg_steps is not None and not pd.isna(avg_steps) else "No data",
            delta=f"{steps_change:+,.0f}" if steps_change is not None else None,
        )
        st.caption(steps_status)

    with col3:
        st.metric(
            "Current Weight",
            kg_to_st_lb(latest_weight_kg) if latest_weight_kg is not None else "No data",
            delta=f"{weight_change_lb:+.1f}lb" if weight_change_lb is not None else None,
        )
        st.caption(weight_status)

    with col4:
        st.metric(
            "Average Protein",
            f"{avg_protein:.0f}g" if avg_protein is not None and not pd.isna(avg_protein) else "No data",
            delta=f"{protein_change:+.0f}g" if protein_change is not None else None,
        )
        st.caption(protein_status)

    st.divider()

    st.markdown("### Today / Yesterday / Last 3 Days")
    st.dataframe(today_table, use_container_width=True, hide_index=True)

    st.divider()

    st.markdown("### Copy-and-Paste Hospital Summary")

    hospital_summary = build_hospital_summary(
        start_date=main_start,
        end_date=main_end,
        goals=goals,
        sleep_range=sleep_range,
        activity_range=activity_range,
        weight_range=weight_range,
        food_daily_range=food_daily_range,
        sleep_change=sleep_change,
        steps_change=steps_change,
        weight_change_lb=weight_change_lb,
        protein_change=protein_change,
        health_notes_df=health_notes_df,
    )

    st.text_area(
        "Hospital summary text",
        hospital_summary,
        height=460,
        key="hospital_summary_text",
    )

    st.divider()

    st.markdown("### Extra Notes For Appointment")

    extra_notes = st.text_area(
        "Type any extra symptoms, concerns or questions here",
        placeholder=(
            "Example: Brain fog has been worse this week. Sleep has been poor. "
            "Pain levels remain high. I would like to ask about the iron infusion and pain clinic referral."
        ),
        height=150,
        key="hospital_extra_notes",
    )

    if extra_notes.strip():
        st.markdown("### Summary With Extra Notes")

        st.text_area(
            "Copy this version",
            hospital_summary + "\n\nAdditional notes:\n" + extra_notes.strip(),
            height=520,
            key="hospital_summary_with_notes",
        )


# ============================================================
# Health Notes tab
# ============================================================

with tabs[6]:
    st.subheader("Health Notes")

    st.caption(
        "Track pain, brain fog, fatigue, mood, sleep quality and appointment questions. "
        "Saved locally in health_notes.csv."
    )

    st.markdown("### Quick Add / Update Today")

    q1, q2, q3, q4 = st.columns(4)

    with q1:
        quick_pain = st.number_input("Pain 0-10", min_value=0, max_value=10, value=0, step=1, key="quick_pain")

    with q2:
        quick_brain_fog = st.number_input("Brain fog 0-10", min_value=0, max_value=10, value=0, step=1, key="quick_brain_fog")

    with q3:
        quick_fatigue = st.number_input("Fatigue 0-10", min_value=0, max_value=10, value=0, step=1, key="quick_fatigue")

    with q4:
        quick_mood = st.text_input("Mood", value="", key="quick_mood")

    quick_sleep_quality = st.text_input("Sleep quality", value="", key="quick_sleep_quality")
    quick_notes = st.text_area("Symptoms / Notes", value="", height=100, key="quick_notes")
    quick_questions = st.text_area("Questions for clinician", value="", height=80, key="quick_questions")

    if st.button("Add / update today's health note", key="add_today_health_note"):
        new_row = {
            "Date": date.today().strftime("%Y-%m-%d"),
            "Pain 0-10": quick_pain,
            "Brain fog 0-10": quick_brain_fog,
            "Fatigue 0-10": quick_fatigue,
            "Mood": quick_mood,
            "Sleep quality": quick_sleep_quality,
            "Symptoms / Notes": quick_notes,
            "Questions for clinician": quick_questions,
        }

        health_notes_df = add_or_update_today_health_note(health_notes_df, new_row)
        st.success("Today's health note has been added or updated. Refresh the app to see it everywhere.")

    st.divider()

    st.markdown("### Symptom Summary")

    if health_notes_chart_df.empty:
        st.info("No symptom scores saved yet.")
    else:
        s1, s2, s3, s4 = st.columns(4)

        with s1:
            avg_pain = health_notes_chart_df["Pain 0-10"].mean()
            st.metric("Average Pain", f"{avg_pain:.1f}/10" if not pd.isna(avg_pain) else "No data")

        with s2:
            avg_brain = health_notes_chart_df["Brain fog 0-10"].mean()
            st.metric("Average Brain Fog", f"{avg_brain:.1f}/10" if not pd.isna(avg_brain) else "No data")

        with s3:
            avg_fatigue = health_notes_chart_df["Fatigue 0-10"].mean()
            st.metric("Average Fatigue", f"{avg_fatigue:.1f}/10" if not pd.isna(avg_fatigue) else "No data")

        with s4:
            st.metric("Days Logged", health_notes_chart_df["date"].nunique())

        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            health_notes_line_chart(
                health_notes_chart_df,
                "Pain 0-10",
                "Pain Trend",
                "health_pain_chart",
            )

            health_notes_line_chart(
                health_notes_chart_df,
                "Fatigue 0-10",
                "Fatigue Trend",
                "health_fatigue_chart",
            )

        with c2:
            health_notes_line_chart(
                health_notes_chart_df,
                "Brain fog 0-10",
                "Brain Fog Trend",
                "health_brain_fog_chart",
            )

            st.markdown("### Symptom Summary For Appointments")
            st.text_area(
                "Copy symptom summary",
                symptom_summary_text(health_notes_df),
                height=220,
                key="symptom_summary_copy",
            )

    st.divider()

    st.markdown("### Edit Health Notes")

    edited_health_notes = st.data_editor(
        health_notes_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="health_notes_editor",
    )

    if st.button("Save health notes", key="save_health_notes_button"):
        save_health_notes(edited_health_notes)
        st.success("Health notes saved and cleaned.")

    st.divider()

    st.markdown("### Copy Recent Health Notes")

    recent_notes_copy = recent_health_notes_text(edited_health_notes, limit=10)

    st.text_area(
        "Recent health notes copy version",
        recent_notes_copy if recent_notes_copy.strip() else "No recent health notes entered yet.",
        height=300,
        key="recent_health_notes_copy",
    )


# ============================================================
# Medication tab
# ============================================================

with tabs[7]:
    st.subheader("Medication List")

    st.caption(
        "This is a simple local medication list for appointments. "
        "Please check it against your prescription labels or clinical letters before sending it anywhere."
    )

    meds_df = load_medications()

    edited_meds = st.data_editor(
        meds_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="medication_editor",
    )

    if st.button("Save medication list", key="save_medication_button"):
        save_medications(edited_meds)
        st.success("Medication list saved.")

    st.divider()

    st.markdown("### Appointment Copy Version")

    if not edited_meds.empty:
        lines = []

        for _, row in edited_meds.sort_values("Medication").iterrows():
            medication = row.get("Medication", "")
            dose = row.get("Dose", "")
            when = row.get("When", "")
            purpose = row.get("What it is for", "")
            notes = row.get("Notes", "")

            line = f"- {medication}, {dose}, {when}"

            if purpose:
                line += f", for {purpose}"

            if notes:
                line += f". Notes: {notes}"

            lines.append(line)

        st.text_area(
            "Copy medication list",
            "\n".join(lines),
            height=300,
            key="medication_copy_text",
        )


# ============================================================
# Appointments tab
# ============================================================

with tabs[8]:
    st.subheader("Appointments")

    st.caption("Use this to keep short appointment summaries and follow-up actions in one place.")

    appt_df = load_appointments()

    edited_appts = st.data_editor(
        appt_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="appointments_editor",
    )

    if st.button("Save appointments", key="save_appointments_button"):
        save_appointments(edited_appts)
        st.success("Appointments saved.")

    st.divider()

    st.markdown("### Appointment Summary Copy Version")

    if not edited_appts.empty:
        try:
            edited_appts["Date_sort"] = pd.to_datetime(edited_appts["Date"], errors="coerce")
            display_appts = edited_appts.sort_values("Date_sort", ascending=False)
        except Exception:
            display_appts = edited_appts.copy()

        appointment_lines = []

        for _, row in display_appts.iterrows():
            appt_date = row.get("Date", "")
            clinic = row.get("Clinic / Service", "")
            location = row.get("Location", "")
            summary = row.get("Summary", "")
            actions = row.get("Follow up / Actions", "")

            appointment_lines.append(
                f"{appt_date}, {clinic}, {location}\n"
                f"Summary: {summary}\n"
                f"Follow up / Actions: {actions}\n"
            )

        st.text_area(
            "Copy appointment summaries",
            "\n".join(appointment_lines),
            height=350,
            key="appointment_copy_text",
        )


# ============================================================
# Goals tab
# ============================================================

with tabs[9]:
    st.subheader("Goals")

    st.caption("These goals are saved locally and used for the small traffic light status checks.")

    col1, col2, col3 = st.columns(3)

    with col1:
        goals["sleep_hours"] = st.number_input(
            "Sleep goal, hours",
            min_value=1.0,
            max_value=12.0,
            value=float(goals["sleep_hours"]),
            step=0.25,
            key="goal_sleep_hours",
        )

        goals["steps"] = st.number_input(
            "Steps goal",
            min_value=0,
            max_value=50000,
            value=int(goals["steps"]),
            step=500,
            key="goal_steps",
        )

        goals["fluids_l"] = st.number_input(
            "Fluid goal, litres",
            min_value=0.0,
            max_value=6.0,
            value=float(goals["fluids_l"]),
            step=0.25,
            key="goal_fluids_l",
        )

    with col2:
        goals["calories"] = st.number_input(
            "Calorie budget",
            min_value=500,
            max_value=5000,
            value=int(goals["calories"]),
            step=50,
            key="goal_calories",
        )

        goals["protein_g"] = st.number_input(
            "Protein goal, grams",
            min_value=0,
            max_value=300,
            value=int(goals["protein_g"]),
            step=5,
            key="goal_protein_g",
        )

        goals["target_weight_stones"] = st.number_input(
            "Target weight, stone",
            min_value=5.0,
            max_value=35.0,
            value=float(goals["target_weight_stones"]),
            step=0.5,
            key="goal_target_weight_stones",
        )

    with col3:
        goals["carbs_pct"] = st.number_input(
            "Carbs target %",
            min_value=0,
            max_value=100,
            value=int(goals["carbs_pct"]),
            step=5,
            key="goal_carbs_pct",
        )

        goals["protein_pct"] = st.number_input(
            "Protein target %",
            min_value=0,
            max_value=100,
            value=int(goals["protein_pct"]),
            step=5,
            key="goal_protein_pct",
        )

        goals["fat_pct"] = st.number_input(
            "Fat target %",
            min_value=0,
            max_value=100,
            value=int(goals["fat_pct"]),
            step=5,
            key="goal_fat_pct",
        )

    total_macro = goals["carbs_pct"] + goals["protein_pct"] + goals["fat_pct"]

    if total_macro != 100:
        st.warning(f"Macro targets currently add up to {total_macro}%. Ideally they should add up to 100%.")
    else:
        st.success("Macro targets add up to 100%.")

    if st.button("Save goals", key="save_goals_button"):
        save_json_file(GOALS_FILE, goals)
        st.success("Goals saved. Refresh the app to apply them everywhere.")

    st.divider()

    st.markdown("### Current Goal Summary")

    st.write(f"Sleep: {human_duration_from_hours(goals['sleep_hours'])}")
    st.write(f"Steps: {goals['steps']:,} per day")
    st.write(f"Calories: {goals['calories']:,} kcal per day")
    st.write(f"Protein: {goals['protein_g']}g per day")
    st.write(
        f"Macros: Carbs {goals['carbs_pct']}%, "
        f"Protein {goals['protein_pct']}%, "
        f"Fat {goals['fat_pct']}%"
    )
    st.write(f"Fluids: {goals['fluids_l']}L per day")
    st.write(f"Target weight: {goals['target_weight_stones']:.1f} stone")