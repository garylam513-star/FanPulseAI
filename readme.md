# ⚡ FANPULSE AI LIVE

**FANPULSE AI LIVE** is a dual-screen, AI-powered live-streaming commerce and fan engagement platform built with **Streamlit**, **PayPal Sandbox Orders v2 API**, and **Google Cloud Vertex AI (Gemini)**.

It showcases a side-by-side **Fan Mobile Interface** and **Influencer Live Studio**, enabling real-time micropayments, merchandise purchases, automated AI cheerleading, and private post-purchase shipping logistics.

---

## ✨ Key Features

### 📱 Fan Mobile Interface (Left Screen)
* **Live Video & Public Stream Chat:** Real-time public chat feed synchronized across both screens.
* **Unified Live Stream Gifts & Store:** Instant checkout for digital gifts (**Heart \$5**, **Flower \$10**, **Custom Donation**) and physical merchandise (**Cup \$15**, **T-Shirt \$55**, **Hat \$35**) via **PayPal Sandbox**.
* **Private Chat with AI Virtual Assistant:** Dedicated 1-on-1 private messaging channel where the influencer's Gemini Virtual Assistant confirms receipts, asks for shipping addresses on physical orders, and provides 2–3 business day shipping timelines.

### 🎙️ Influencer Live Studio (Right Screen)
* **Live Transaction Ledger (AG Grid):** Interactive, sortable, and filterable data grid tracking incoming fan gifts, donations, and merch orders (`⏳ Pending` → `✅ Completed`).
* **Control Room Feed:** Live monitor of public stream chat and AI Virtual Assistant shoutouts.
* **Live Diagnostic Streams (Toggleable):** Built-in toggles (off by default) to inspect raw **PayPal Sandbox API** payloads and **Vertex AI Gemini** token/status logs in real time.

### 🤖 Dual-Role Gemini Virtual Assistant
* **Public Cheerleader & Hype Co-Host:** Automatically celebrates every completed PayPal transaction in public chat and randomly triggers bonus fan rewards (such as song requests or instant stream lucky draws).
* **Private Logistics Coordinator:** Handles conversational order follow-ups, collects fan shipping addresses, and confirms fulfillment timelines in Private Chat.

---

## 🛠️ Tech Stack

* **Frontend / App Framework:** Python, Streamlit, `streamlit-aggrid`, Pandas
* **Payments:** PayPal REST API v2 (`https://paypal.com` — OAuth 2.0 Client Credentials + Checkout Orders v2 Creation & Auto-Capture)
* **Generative AI:** Google Cloud Vertex AI (`google-genai`, `google-auth`, `gemini-2.5-flash`)
* **Hosting:** Local Windows / Render Cloud Web Service

---

## 🚀 Local Setup (Windows)

### 1. Install Dependencies
```cmd
py -m pip install -r requirements.txt
```

### 2. Configure Credentials
Create a `.env` file in the project root (`C:\FanPulseAI\.env`) with your PayPal Sandbox credentials:
```env
PAYPAL_CLIENT_ID=your_paypal_sandbox_client_id
PAYPAL_SECRET=your_paypal_sandbox_secret
```

Place your Google Cloud Service Account JSON key file in the project root and name it:
```text
gcp_key.json
```
*(Ensure **Vertex AI API** / `://googleapis.com` is enabled on your GCP project and your service account has the **Vertex AI User** / **Agent Platform User** role.)*

### 3. Run the Application
```cmd
py -m streamlit run app.py
```
Open `http://localhost:8501` in your browser.

---

## ☁️ Deploying to Render

1. Push `app.py`, `requirements.txt`, `Procfile`, and `README.md` to your GitHub repository. *(Do **not** commit `.env` or `gcp_key.json`—add both to `.gitignore`.)*
2. Create a new **Web Service** on [Render](https://render.com) connected to your GitHub repo.
3. Add the following **Environment Variables** in Render's dashboard:

| Key | Value |
| :--- | :--- |
| `PAYPAL_CLIENT_ID` | Your PayPal Sandbox Client ID |
| `PAYPAL_SECRET` | Your PayPal Sandbox Secret |
| `GCP_CREDENTIALS_JSON` | Full JSON contents of your `gcp_key.json` file |
| `GCP_LOCATION` | `global` (or `us-central1`) |

4. Deploy! Render automatically sets `RENDER_EXTERNAL_URL` so PayPal redirects back to your live cloud app after checkout.

---

## 📂 Project Structure

```text
├── app.py              # Main Streamlit application (Fan & Influencer dual UI, PayPal v2, Vertex AI Gemini)
├── requirements.txt    # Python dependencies
├── Procfile            # Render process start command
├── README.md           # Project documentation
├── .gitignore          # Excludes .env and gcp_key.json from version control
├── .env                # Local PayPal credentials (ignored by Git)
└── gcp_key.json        # Local GCP Service Account JSON key (ignored by Git)
```
