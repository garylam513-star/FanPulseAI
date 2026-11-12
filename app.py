import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import random
import requests
from dotenv import load_dotenv
from st_aggrid import AgGrid, GridOptionsBuilder
from google import genai
from google.genai import types
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest
import time
import google.auth.jwt
import google.auth.crypt
from google.oauth2.credentials import Credentials as OAuth2Credentials


load_dotenv()

APP_VERSION = "2.4.0"

# ==============================================================================
# AUTO ENVIRONMENT & CREDENTIAL CONFIGURATION
# ==============================================================================
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID") or "PASTE_YOUR_SANDBOX_CLIENT_ID_HERE"
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET") or "PASTE_YOUR_SANDBOX_SECRET_HERE"
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"


# GCP Vertex AI Configuration (Uses $300 GCP Free Trial Credits)
GCP_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(os.path.dirname(__file__), "gcp_key.json")
GCP_CREDENTIALS_JSON = os.getenv("GCP_CREDENTIALS_JSON")
##GCP_LOCATION = os.getenv("GCP_LOCATION") or "us-central1"
GCP_LOCATION = os.getenv("GCP_LOCATION") or "global"

GEMINI_MODEL = "gemini-3.5-flash-lite"

# Auto-detect Render production URL vs Local Windows URL
APP_BASE_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_BASE_URL") or "http://localhost:8501"
IS_RENDER = bool(os.getenv("RENDER"))

st.set_page_config(
    page_title=f"FANPULSE AI LIVE v{APP_VERSION}",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# PERSISTENT SERVER STORE (SURVIVES PAYPAL BROWSER REDIRECTS)
# ==============================================================================
@st.cache_resource
def get_live_store():
    return {
        "messages": [
            {"user": "System", "text": "Welcome to FANPULSE AI LIVE stream!", "time": "18:00:00"}
        ],
        "private_messages": [
            {"user": "Influencer_VA", "text": "👋 Hi @Fan_User! I'm the influencer's AI Virtual Assistant. Ask me anything or check your store orders here!", "time": "18:00:00"}
        ],
        "transactions": [
            {"Timestamp": "18:00:00", "Fan": "System", "Action/Gift": "Stream Started", "Amount ($)": 0.0, "Status": "✅ Active", "Order ID": "INIT"}
        ],
        "pending_orders": {},
        "captured_orders": set(),
        "is_live": True,
        "last_api_response": None,
        "last_gemini_log": {"status": "IDLE", "details": "No Vertex AI Gemini calls triggered yet."}
    }

store = get_live_store()

if "checkout_link" not in st.session_state:
    st.session_state.checkout_link = None

# ==============================================================================
# GCP VERTEX AI GEMINI VIRTUAL ASSISTANT HELPERS (SPENDS $300 FREE TRIAL CREDITS)
# ==============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "PASTE_YOUR_AQ_KEY_HERE"

def get_gemini_client():
    """Exchanges Service Account JSON for a GCP OAuth2 access_token and initializes Vertex AI."""
    try:
        creds_info = None
        source = "None"
        if GCP_CREDENTIALS_JSON and GCP_CREDENTIALS_JSON.strip().startswith("{"):
            creds_info = json.loads(GCP_CREDENTIALS_JSON)
            source = "GCP_CREDENTIALS_JSON env var"
        elif os.path.exists(GCP_KEY_FILE):
            with open(GCP_KEY_FILE, "r", encoding="utf-8") as f:
                creds_info = json.load(f)
            source = f"Local file ({GCP_KEY_FILE})"

        if not creds_info:
            store["last_gemini_log"] = {"status": "UNCONFIGURED", "error": f"No GCP JSON key found at: {GCP_KEY_FILE}"}
            return None

        if "private_key" in creds_info and isinstance(creds_info["private_key"], str):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")

        # Pull token_uri directly from the JSON key to avoid hardcoded URL issues
        # token_uri = creds_info.get("token_uri") or "https://googleapis.com"
        #scope_url = "https://googleapis.com"
        # scope_url = "https://" + "://googleapis.com" + "/auth/cloud-platform"
        token_uri = creds_info.get("token_uri")
        #scope_url = "/".join(["https:", "", "://googleapis.com", "auth", "cloud-platform"])
        scope_url = "https://www." + "googleapis.com/auth/cloud-platform"



        signer = google.auth.crypt.RSASigner.from_service_account_info(creds_info)
        now = int(time.time())
        claim = {
            "iss": creds_info["client_email"],
            "sub": creds_info["client_email"],
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
            "scope": scope_url
        }

        assertion = google.auth.jwt.encode(signer, claim)
        resp = requests.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion
            },
            timeout=10
        ).json()

        access_token = resp.get("access_token")
        if not access_token:
            store["last_gemini_log"] = {
                "status": "CLIENT_INIT_ERROR",
                "scope_used": scope_url,
                "token_uri_used": token_uri,
                "error": f"Token exchange failed: {resp}"
            }
            return None

        #access_token = resp.get("access_token")
        #if not access_token:
        #    store["last_gemini_log"] = {"status": "CLIENT_INIT_ERROR", "error": f"Token exchange failed: {resp}"}
        #    return None

        credentials = OAuth2Credentials(token=access_token)
        project_id = creds_info.get("project_id")

        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=GCP_LOCATION,
            credentials=credentials
        )
        if store["last_gemini_log"].get("status") in ("IDLE", "UNCONFIGURED", "CLIENT_INIT_ERROR"):
            store["last_gemini_log"] = {
                "status": "VERTEX_AI_READY",
                "source": source,
                "project_id": project_id,
                "location": GCP_LOCATION,
                "model": GEMINI_MODEL
            }
        return client
    except Exception as e:
        store["last_gemini_log"] = {"status": "CLIENT_INIT_ERROR", "error": str(e)}
        return None



def call_gemini(prompt, system_instruction, temperature=0.7):
    """Executes live Vertex AI Gemini call using $300 GCP Free Trial credits."""
    client = get_gemini_client()
    if not client:
        return None

    now = datetime.now().strftime("%H:%M:%S")
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature
            )
        )
        if response and response.text:
            tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", "N/A")
            store["last_gemini_log"] = {
                "timestamp": now,
                "status": "SUCCESS (LIVE VERTEX AI)",
                "model": GEMINI_MODEL,
                "location": GCP_LOCATION,
                "total_tokens": tokens,
                "reply_preview": response.text.strip()[:120]
            }
            return response.text.strip()

        store["last_gemini_log"] = {
            "timestamp": now,
            "status": "EMPTY_RESPONSE",
            "model": GEMINI_MODEL,
            "error": "Vertex AI returned an empty response."
        }
        return None
    except Exception as e:
        store["last_gemini_log"] = {
            "timestamp": now,
            "status": "API_CALL_ERROR (USING FALLBACK)",
            "model": GEMINI_MODEL,
            "location": GCP_LOCATION,
            "error": str(e)
        }
        return None


def generate_public_cheer_message(fan_name, item_label, amount_val):
    grant_bonus = random.choice([True, False])
    bonus_instruction = (
        "Also include a fun surprise reward right now: either ask the influencer to sing a quick song for them OR announce they won an instant stream lucky draw!"
        if grant_bonus else
        "Keep it focused on hyping up the chat and thanking them warmly."
    )

    prompt = (
        f"Fan '{fan_name}' just completed a PayPal purchase of '{item_label}' for ${amount_val:.2f} during a live stream. "
        f"Write a short, energetic, hype 1-2 sentence public stream chat shoutout cheering them up. {bonus_instruction}"
    )
    sys_inst = (
        "You are the energetic AI Cheerleader & Hype Co-Host for a live-streaming influencer on FANPULSE AI LIVE. "
        "Use fun emojis, keep messages punchy (under 35 words), and make fans feel like VIPs."
    )

    ai_text = call_gemini(prompt, sys_inst, temperature=0.8)
    if ai_text:
        return ai_text

    if grant_bonus:
        return f"🎉 HUGE shoutout to @{fan_name} for the {item_label} (${amount_val:.2f})! 🎤 Influencer, sing a verse for @{fan_name} — you just won our instant stream lucky draw! ✨"
    return f"🔥 Let's go @{fan_name}! Thank you so much for the {item_label} (${amount_val:.2f})! Drop some hype in the chat! 💖"

def generate_private_order_followup(fan_name, item_label, amount_val, order_id):
    is_physical = any(k in item_label.lower() for k in ["cup", "t-shirt", "hat"])

    if is_physical:
        prompt = (
            f"Fan '{fan_name}' just paid ${amount_val:.2f} (PayPal Order ID: {order_id}) for physical merch: '{item_label}'. "
            "Write a friendly, concise private message confirming their payment, letting them know the order will ship out in 2-3 business days, "
            "and politely asking them to reply here with their full shipping address."
        )
    else:
        prompt = (
            f"Fan '{fan_name}' just paid ${amount_val:.2f} (PayPal Order ID: {order_id}) for live support: '{item_label}'. "
            "Write a warm, human-sounding 2-sentence private thank-you receipt confirming their support went straight to the influencer."
        )

    sys_inst = (
        "You are the Influencer's dedicated AI Virtual Assistant & Store Logistics Manager on FANPULSE AI LIVE. "
        "You handle order confirmations, shipping timelines (always 2-3 business days for merch), and collecting fan shipping addresses politely."
    )

    ai_text = call_gemini(prompt, sys_inst, temperature=0.5)
    if ai_text:
        return ai_text

    if is_physical:
        return (
            f"✅ Payment confirmed for your {item_label} (${amount_val:.2f}, Order #{order_id})! "
            "Your merch will be packed and shipped out within 2–3 business days. Please reply here with your shipping address so I can lock in your delivery!"
        )
    return f"💖 Thank you @{fan_name}! Your ${amount_val:.2f} support for {item_label} (Order #{order_id}) is confirmed and delivered to the influencer!"

def generate_private_chat_reply(fan_name, fan_message):
    recent_history = "\n".join(
        [f"{m['user']}: {m['text']}" for m in store["private_messages"][-6:]]
    )
    prompt = (
        f"Recent private chat history:\n{recent_history}\n\n"
        f"Latest message from {fan_name}: {fan_message}\n\n"
        "Respond naturally as the influencer's Virtual Assistant. If the fan provided a shipping address, confirm the address looks great, "
        "reiterate that their merch order will ship within 2-3 business days with tracking, and ask if they need anything else."
    )
    sys_inst = (
        "You are the Influencer's AI Virtual Assistant & Logistics Coordinator on FANPULSE AI LIVE. "
        "Manage store orders (Cup, T-Shirt, Hat), confirm shipping addresses clearly, and state that orders ship in 2-3 business days. Keep replies warm and concise."
    )

    ai_text = call_gemini(prompt, sys_inst, temperature=0.5)
    if ai_text:
        return ai_text

    return "📦 Got it! I've updated your shipping details in our fulfillment system. Your order will ship out within 2–3 business days! Let me know if you need anything else."



# ==============================================================================
# PAYPAL SANDBOX API HELPERS (https://paypal.com)
# ==============================================================================
def get_paypal_access_token():
    if "PASTE_YOUR_" in PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_ID.strip():
        return {"error": "Credentials not configured."}
    try:
        url = f"{PAYPAL_API_URL}/v1/oauth2/token"
        headers = {"Accept": "application/json", "Accept-Language": "en_US"}
        data = {"grant_type": "client_credentials"}
        response = requests.post(
            url,
            auth=(PAYPAL_CLIENT_ID.strip(), PAYPAL_SECRET.strip()),
            headers=headers,
            data=data,
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        return {"error": f"HTTP {response.status_code}", "response": response.json()}
    except Exception as e:
        return {"error": str(e)}

def create_paypal_order(item_name, amount_val):
    token = get_paypal_access_token()
    if not token or isinstance(token, dict):
        return {"error": "Handshake Authentication Failed", "details": token}

    url = f"{PAYPAL_API_URL}/v2/checkout/orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "description": f"FanPulse AI Live - {item_name}",
            "amount": {
                "currency_code": "USD",
                "value": f"{amount_val:.2f}"
            }
        }],
        "application_context": {
            "return_url": APP_BASE_URL,
            "cancel_url": f"{APP_BASE_URL}?cancel=true"
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"HTTP {response.status_code}", "response": response.json()}
    except Exception as e:
        return {"error": str(e)}

def get_paypal_order_details(order_id, token):
    url = f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {}

def capture_paypal_order(order_id):
    token = get_paypal_access_token()
    if not token or isinstance(token, dict):
        return {"error": "Handshake Authentication Failed", "details": token}

    order_details = get_paypal_order_details(order_id, token)
    raw_desc = ""
    try:
        raw_desc = order_details["purchase_units"][0].get("description", "")
    except Exception:
        pass

    url = f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}/capture"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(url, headers=headers, timeout=10)
        data = response.json()
        if isinstance(data, dict) and raw_desc:
            data["_item_description"] = raw_desc
        if response.status_code in (200, 201):
            return data
        return {"error": f"HTTP {response.status_code}", "response": data}
    except Exception as e:
        return {"error": str(e)}

def format_completed_chat_announcement(fan_name, item_label, amount_val):
    label_lower = item_label.lower()
    if "heart" in label_lower:
        return f"❤️ fan {fan_name} sent heart (${amount_val:.2f}) to influencer!"
    if "flower" in label_lower:
        return f"🌸 fan {fan_name} sent flower (${amount_val:.2f}) to influencer!"
    if "donation" in label_lower:
        return f"💰 fan {fan_name} donated ${amount_val:.2f} to influencer!"
    if "cup" in label_lower:
        return f"🥛 fan {fan_name} ordered Cup (${amount_val:.2f}) from influencer store!"
    if "t-shirt" in label_lower:
        return f"👕 fan {fan_name} ordered T-Shirt (${amount_val:.2f}) from influencer store!"
    if "hat" in label_lower:
        return f"🧢 fan {fan_name} ordered Hat (${amount_val:.2f}) from influencer store!"
    return f"🎉 fan {fan_name} sent {item_label} (${amount_val:.2f}) to influencer!"

# ==============================================================================
# AUTO-CAPTURE WHEN RETURNING FROM PAYPAL SANDBOX CHECKOUT
# ==============================================================================
query_params = st.query_params
returned_token = query_params.get("token")
is_cancelled = query_params.get("cancel")

if is_cancelled:
    st.session_state.checkout_link = None
    st.query_params.clear()
    st.warning("Payment was cancelled by fan.")

elif returned_token and returned_token not in store["captured_orders"]:
    with st.spinner("Finalizing PayPal payment capture & notifying AI Virtual Assistant..."):
        capture_res = capture_paypal_order(returned_token)
        store["last_api_response"] = capture_res
        store["captured_orders"].add(returned_token)
        st.session_state.checkout_link = None

        now = datetime.now().strftime("%H:%M:%S")
        order_meta = store["pending_orders"].get(returned_token, {})

        if isinstance(capture_res, dict) and capture_res.get("status") == "COMPLETED":
            try:
                pu = capture_res["purchase_units"][0]
                capture_info = pu["payments"]["captures"][0]
                settled_val = float(capture_info["amount"]["value"])
            except Exception:
                settled_val = float(order_meta.get("amount", 0.0))

            raw_desc = capture_res.get("_item_description", "")
            item_label = (
                raw_desc.replace("FanPulse AI Live - ", "")
                if raw_desc
                else order_meta.get("item", "Live Support")
            )

            updated = False
            for tx in store["transactions"]:
                if tx.get("Order ID") == returned_token:
                    tx["Status"] = "✅ Completed"
                    tx["Amount ($)"] = settled_val
                    tx["Action/Gift"] = item_label
                    updated = True
                    break

            if not updated:
                store["transactions"].append({
                    "Timestamp": now,
                    "Fan": "Fan_User",
                    "Action/Gift": item_label,
                    "Amount ($)": settled_val,
                    "Status": "✅ Completed",
                    "Order ID": returned_token
                })

            chat_announcement = format_completed_chat_announcement("Fan_User", item_label, settled_val)
            store["messages"].append({
                "user": "System",
                "text": chat_announcement,
                "time": now
            })

            public_cheer = generate_public_cheer_message("Fan_User", item_label, settled_val)
            store["messages"].append({
                "user": "Influencer_VA",
                "text": public_cheer,
                "time": now
            })

            private_followup = generate_private_order_followup("Fan_User", item_label, settled_val, returned_token)
            store["private_messages"].append({
                "user": "Influencer_VA",
                "text": private_followup,
                "time": now
            })
        else:
            store["messages"].append({
                "user": "System",
                "text": f"⚠️ Order {returned_token} returned, but capture was not completed.",
                "time": now
            })

        st.query_params.clear()
        st.rerun()

# ==============================================================================
# PURCHASE CLICK HANDLER (NO PENDING SPAM IN CHAT)
# ==============================================================================
def handle_purchase_click(item_name, cost):
    with st.spinner("Contacting PayPal Sandbox..."):
        res = create_paypal_order(item_name, cost)
        store["last_api_response"] = res

        if isinstance(res, dict) and "id" in res:
            order_id = res["id"]
            approve_url = next((link["href"] for link in res["links"] if link["rel"] == "approve"), None)
            st.session_state.checkout_link = approve_url
            store["pending_orders"][order_id] = {"item": item_name, "amount": float(cost)}

            now = datetime.now().strftime("%H:%M:%S")
            store["transactions"].append({
                "Timestamp": now,
                "Fan": "Fan_User",
                "Action/Gift": item_name,
                "Amount ($)": float(cost),
                "Status": "⏳ Pending",
                "Order ID": order_id
            })
        else:
            st.error("Initialization Failed. Enable the Diagnostic Stream on the Influencer panel to inspect.")

# ==============================================================================
# COMPACT TOP BANNER
# ==============================================================================
col_title, col_ver = st.columns([0.85, 0.15])
with col_title:
    st.markdown("<h3 style='margin:0; padding:0;'>⚡ FANPULSE AI LIVE</h3>", unsafe_allow_html=True)
with col_ver:
    env_label = "Render Cloud" if IS_RENDER else "Local Windows"
    st.markdown(
        f"<div style='text-align: right; color: #555555; font-weight: bold; font-size:0.95rem;'>v{APP_VERSION} ({env_label})</div>",
        unsafe_allow_html=True
    )

token_check = get_paypal_access_token()
gemini_ready = get_gemini_client() is not None

status_parts = []
if token_check and not isinstance(token_check, dict):
    status_parts.append(f"✅ PayPal Sandbox Connected ({APP_BASE_URL})")
else:
    status_parts.append("⚠️ PayPal Unconfigured")

if gemini_ready:
    status_parts.append(f"✅ Gemini Credentials Loaded ({GEMINI_MODEL})")
else:
    status_parts.append("⚠️ GCP JSON Key Missing (Fallback Mode)")

if (token_check and not isinstance(token_check, dict)) and gemini_ready:
    st.success(" | ".join(status_parts))
else:
    st.warning(" | ".join(status_parts))

st.divider()

# ==============================================================================
# DUAL SCREEN LAYOUT
# ==============================================================================
col_fan, col_divider, col_influencer = st.columns([0.475, 0.05, 0.475], gap="small")

# --- LEFT SIDE: FAN SCREEN ---
with col_fan:
    st.subheader("📱 Fan Mobile Interface")
    if store["is_live"]:
        st.info("🔴 LIVE NOW — Engaging with Fans via Gemini AI")
    else:
        st.warning("⏳ OFFLINE")

    st.video("https://youtube.com")

    # Public Stream Chat
    st.markdown("##### 💬 Stream Chat")
    fan_chat_html = "<div style='height:125px; overflow-y:auto; border:1px solid #CCC; padding:8px; border-radius:4px; display:flex; flex-direction:column-reverse; font-size:0.9rem; color:#000; background:#FFF;'>"
    for m in reversed(store["messages"]):
        fan_chat_html += f"<p style='margin:2px 0;'><strong>[{m['time']}] @{m['user']}:</strong> {m['text']}</p>"
    st.components.v1.html(fan_chat_html + "</div>", height=140)

    # Private Chat with Influencer's Gemini Virtual Assistant
    st.markdown("##### 🔒 Private Chat (with AI Virtual Assistant)")
    priv_chat_html = "<div style='height:135px; overflow-y:auto; border:1px solid #0070BA; padding:8px; border-radius:4px; display:flex; flex-direction:column-reverse; font-size:0.9rem; color:#000; background:#F4F9FF;'>"
    for pm in reversed(store["private_messages"]):
        priv_chat_html += f"<p style='margin:2px 0;'><strong>[{pm['time']}] @{pm['user']}:</strong> {pm['text']}</p>"
    st.components.v1.html(priv_chat_html + "</div>", height=150)

    with st.form("private_chat_form", clear_on_submit=True):
        p_col1, p_col2 = st.columns([0.78, 0.22])
        with p_col1:
            priv_msg = st.text_input("Private message to Virtual Assistant...", placeholder="Reply with shipping address or ask about your order...", label_visibility="collapsed")
        with p_col2:
            send_priv = st.form_submit_button("Reply", use_container_width=True)
        if send_priv and priv_msg:
            now = datetime.now().strftime("%H:%M:%S")
            store["private_messages"].append({"user": "Fan_User", "text": priv_msg, "time": now})
            with st.spinner("Virtual Assistant is typing..."):
                va_reply = generate_private_chat_reply("Fan_User", priv_msg)
            store["private_messages"].append({"user": "Influencer_VA", "text": va_reply, "time": datetime.now().strftime("%H:%M:%S")})
            st.rerun()

    # Unified Live Stream Gifts and Store Section
    st.markdown("### 🎁 Live Stream Gifts and Store")
    col_d1, col_d2, col_d3 = st.columns([1, 1, 1.5])
    with col_d1:
        if st.button("❤️ Heart ($5)", use_container_width=True):
            handle_purchase_click("Heart Gift", 5.0)
    with col_d2:
        if st.button("🌸 Flower ($10)", use_container_width=True):
            handle_purchase_click("Flower Gift", 10.0)
    with col_d3:
        donation = st.number_input("Custom ($)", min_value=1.0, value=10.0, step=1.0, label_visibility="collapsed")
        if st.button("💰 Donate", use_container_width=True):
            handle_purchase_click("Custom Donation", donation)

    s1, s2, s3 = st.columns(3)
    with s1:
        if st.button("🥛 Order Cup ($15)", use_container_width=True):
            handle_purchase_click("Merch Cup", 15.0)
    with s2:
        if st.button("👕 Order T-Shirt ($55)", use_container_width=True):
            handle_purchase_click("Merch T-Shirt", 55.0)
    with s3:
        if st.button("🧢 Order Hat ($35)", use_container_width=True):
            handle_purchase_click("Merch Hat", 35.0)

    if st.session_state.checkout_link:
        st.markdown("<div style='border:2px dashed #0070BA; padding:10px; border-radius:6px; margin-top:10px;'>", unsafe_allow_html=True)
        st.link_button("🔒 Confirm & Pay via secure PayPal Sandbox Gateway", st.session_state.checkout_link, use_container_width=True)
        if st.button("❌ Cancel Open Payment Action", use_container_width=True):
            st.session_state.checkout_link = None
            store["last_api_response"] = None
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Public Stream Chat Input
    st.markdown("#### ✉️ Send a Public Message")
    with st.form("chat_form", clear_on_submit=True):
        msg = st.text_input("Type your public message...", placeholder="Hello!")
        if st.form_submit_button("Send Message", use_container_width=True) and msg:
            now = datetime.now().strftime("%H:%M:%S")
            store["messages"].append({"user": "Fan_User", "text": msg, "time": now})
            st.rerun()

# --- MIDDLE COLUMN: VERTICAL DIVIDER ---
with col_divider:
    st.markdown("<div style='border-left:2px solid #CCC; height:155vh; margin:0 auto; width:2px;'></div>", unsafe_allow_html=True)

# --- RIGHT SIDE: INFLUENCER SCREEN ---
with col_influencer:
    st.subheader("🎙️ Influencer Live Studio")
    st.markdown("### 📊 Live Transaction Ledger")

    tx_df = pd.DataFrame(store["transactions"])
    display_cols = [c for c in tx_df.columns if c != "Order ID"]
    ledger_df = tx_df[display_cols].iloc[::-1].reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(ledger_df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    gb.configure_column("Timestamp", width=95)
    gb.configure_column("Fan", width=100)
    gb.configure_column("Action/Gift", width=140)
    gb.configure_column("Amount ($)", width=105, type=["numericColumn", "numberColumnFilter"], precision=2)
    gb.configure_column("Status", width=115)
    grid_options = gb.build()

    AgGrid(
        ledger_df,
        gridOptions=grid_options,
        height=220,
        fit_columns_on_grid_load=True,
        theme="streamlit",
        key=f"ledger_grid_{len(ledger_df)}_{sum(1 for t in store['transactions'] if 'Completed' in t['Status'])}"
    )

    st.markdown("### 💻 Control Room Feed")
    studio_chat_html = "<div style='height:160px; overflow-y:auto; border:1px solid #999; padding:10px; border-radius:4px; display:flex; flex-direction:column-reverse; color:#000; background:#FAFAFA;'>"
    for m in reversed(store["messages"]):
        studio_chat_html += f"<p style='margin:4px 0;'><strong>[{m['time']}] @{m['user']}:</strong> {m['text']}</p>"
    st.components.v1.html(studio_chat_html + "</div>", height=175)

    st.markdown("### 📅 Next Broadcast Setting")
    if st.button("🔄 Toggle Stream Status", use_container_width=True):
        store["is_live"] = not store["is_live"]
        st.rerun()

    st.divider()

    # Diagnostic 1: PayPal Sandbox API Diagnostic Stream (Default Off)
    st.markdown("### 🔍 Live PayPal Sandbox API Diagnostic Stream")
    enable_diagnostics = st.toggle("Enable PayPal API Diagnostic Stream", value=False)
    if enable_diagnostics:
        if store["last_api_response"]:
            st.json(store["last_api_response"])
        else:
            st.caption("Diagnostic Stream enabled. Click any gift or store button on the left to inspect raw API payloads.")

    st.divider()

    # Diagnostic 2: Live AI Status & Error Log (Default Off)
    st.markdown("### 🤖 Live AI Status & Error Log")
    enable_ai_log = st.toggle("Enable Live AI Status & Error Log", value=False)
    if enable_ai_log:
        st.json(store["last_gemini_log"])
