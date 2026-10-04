import json
import streamlit as st
from twilio.rest import Client

account_sid = st.secrets["TWILIO_ACCOUNT_SID"]
auth_token = st.secrets["TWILIO_AUTH_TOKEN"]
content_sid = st.secrets["TWILIO_CONTENT_SID"]

client = Client(
    account_sid,
    auth_token
)

message = client.messages.create(
    from_=st.secrets["TWILIO_WHATSAPP_FROM"],
    to="whatsapp:+919989733197",
    content_sid=content_sid,
    content_variables=json.dumps({
        "1": "tomorrow",
        "2": "12:00 PM"
    })
)

print("SUCCESS!")
print("Message SID:", message.sid)