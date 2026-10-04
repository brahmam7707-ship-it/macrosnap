import re
import json
import smtplib
from datetime import date

from email.mime.text import MIMEText

import pandas as pd
import streamlit as st

from google import genai
from google.genai import types

from twilio.rest import Client


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="MacroSnap",
    page_icon="🥗",
    layout="centered"
)

# =========================================================
# DAILY TRACKING
# =========================================================

if "daily_calories_consumed" not in st.session_state:
    st.session_state.daily_calories_consumed = 0.0

if "daily_protein_consumed" not in st.session_state:
    st.session_state.daily_protein_consumed = 0.0


# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown("""
<style>

.main-title {
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    margin-bottom: 5px;
}

.subtitle {
    text-align: center;
    color: #666;
    font-size: 17px;
    margin-bottom: 30px;
}

.result-box {
    padding: 20px;
    border-radius: 15px;
    background-color: #f7f7f7;
    margin-top: 20px;
}

.target-box {
    padding: 18px;
    border-radius: 15px;
    background-color: #f5f5f5;
    margin-top: 10px;
    margin-bottom: 15px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="main-title">🥗 MacroSnap</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Snap your food. Know your macros. Tailored to your goals.'
    '</div>',
    unsafe_allow_html=True
)

# =========================================================
# DAILY FOOD TRACKING
# =========================================================

if "daily_calories_consumed" not in st.session_state:
    st.session_state.daily_calories_consumed = 0.0

if "daily_protein_consumed" not in st.session_state:
    st.session_state.daily_protein_consumed = 0.0

if "food_history" not in st.session_state:
    st.session_state.food_history = []

if "meal_history" not in st.session_state:
    st.session_state.meal_history = []

# Automatically reset meals when a new day starts
today = str(date.today())

if "tracking_date" not in st.session_state:
    st.session_state.tracking_date = today

if st.session_state.tracking_date != today:
    st.session_state.meal_history = []
    st.session_state.daily_calories_consumed = 0.0
    st.session_state.daily_protein_consumed = 0.0
    st.session_state.tracking_date = today


# =========================================================
# GEMINI CLIENT
# =========================================================

@st.cache_resource
def get_gemini_client():

    return genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"]
    )


client = get_gemini_client()


# =========================================================
# EMAIL FUNCTION
# =========================================================

def send_email(to_address, subject, body):

    gmail_address = st.secrets["GMAIL_ADDRESS"]
    gmail_app_password = st.secrets["GMAIL_APP_PASSWORD"]

    message = MIMEText(body)

    message["Subject"] = subject
    message["From"] = gmail_address
    message["To"] = to_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:

        server.login(
            gmail_address,
            gmail_app_password
        )

        server.send_message(message)
# =========================================================
# WHATSAPP FUNCTION
# =========================================================

def send_whatsapp(to_number, message_body):

    account_sid = st.secrets["TWILIO_ACCOUNT_SID"]
    auth_token = st.secrets["TWILIO_AUTH_TOKEN"]
    whatsapp_from = st.secrets["TWILIO_WHATSAPP_FROM"]
    content_sid = st.secrets["TWILIO_CONTENT_SID"]

    twilio_client = Client(account_sid, auth_token)

    if to_number.startswith("whatsapp:"):
        whatsapp_to = to_number
    else:
        whatsapp_to = f"whatsapp:{to_number}"

    message = twilio_client.messages.create(
        from_=whatsapp_from,
        to=whatsapp_to,
        content_sid=content_sid,
        content_variables=json.dumps({
            "1": "MacroSnap",
            "2": "Nutrition Report"
        })
    )

    return message.sid
# =========================================================
# CALCULATE DAILY NUTRITION TARGETS
# =========================================================

def calculate_daily_targets(
    weight,
    height,
    age,
    sex,
    activity,
    goal
):

    # -----------------------------------------------------
    # BMR calculation
    # Mifflin-St Jeor equation
    # -----------------------------------------------------

    if sex == "Male":

        bmr = (
            10 * weight
            + 6.25 * height
            - 5 * age
            + 5
        )

    elif sex == "Female":

        bmr = (
            10 * weight
            + 6.25 * height
            - 5 * age
            - 161
        )

    else:

        # Neutral estimate when sex is not specified
        bmr = (
            10 * weight
            + 6.25 * height
            - 5 * age
            - 78
        )

    # -----------------------------------------------------
    # Activity multiplier
    # -----------------------------------------------------

    activity_multipliers = {

        "Sedentary": 1.2,

        "Lightly Active": 1.375,

        "Moderately Active": 1.55,

        "Very Active": 1.725

    }

    activity_factor = activity_multipliers.get(
        activity,
        1.2
    )

    # -----------------------------------------------------
    # Estimated maintenance calories
    # -----------------------------------------------------

    maintenance_calories = bmr * activity_factor

    # -----------------------------------------------------
    # Goal adjustment
    # -----------------------------------------------------

    if goal == "Lose Weight":

        daily_calories = maintenance_calories * 0.85

    elif goal == "Gain Weight":

        daily_calories = maintenance_calories * 1.10

    else:

        daily_calories = maintenance_calories

    # -----------------------------------------------------
    # Protein target
    # Simple project estimate:
    # approximately 1.6 g per kg body weight
    # -----------------------------------------------------

    protein_target = weight * 1.6

    # -----------------------------------------------------
    # Water target
    # approximately 35 ml per kg body weight
    # -----------------------------------------------------

    water_target = weight * 0.035

    # -----------------------------------------------------
    # Prevent unrealistic display values
    # -----------------------------------------------------

    daily_calories = max(
        1200,
        min(daily_calories, 5000)
    )

    protein_target = max(
        40,
        min(protein_target, 300)
    )

    water_target = max(
        1.5,
        min(water_target, 6.0)
    )

    return {
        "calories": round(daily_calories),
        "protein": round(protein_target),
        "water": round(water_target, 1)
    }


# =========================================================
# NUTRITION PARSER
# =========================================================

def extract_nutrition(text):

    calories = re.search(
        r"CALORIES:\s*([\d.]+)",
        text,
        re.I
    )

    protein = re.search(
        r"PROTEIN:\s*([\d.]+)",
        text,
        re.I
    )

    carbs = re.search(
        r"CARBS:\s*([\d.]+)",
        text,
        re.I
    )

    fat = re.search(
        r"FAT:\s*([\d.]+)",
        text,
        re.I
    )

    food = re.search(
        r"FOOD:\s*(.+)",
        text,
        re.I
    )

    serving = re.search(
        r"SERVING:\s*(.+)",
        text,
        re.I
    )

    description = re.search(
        r"DESCRIPTION:\s*(.+)",
        text,
        re.I
    )

    recommendation = re.search(
        r"RECOMMENDATION:\s*(.+)",
        text,
        re.I
    )

    return {

        "food":
            food.group(1).strip()
            if food else "Unknown",

        "serving":
            serving.group(1).strip()
            if serving else "Estimated serving",

        "calories":
            calories.group(1)
            if calories else "N/A",

        "protein":
            protein.group(1)
            if protein else "N/A",

        "carbs":
            carbs.group(1)
            if carbs else "N/A",

        "fat":
            fat.group(1)
            if fat else "N/A",

        "description":
            description.group(1).strip()
            if description else "",

        "recommendation":
            recommendation.group(1).strip()
            if recommendation else ""

    }


# =========================================================
# GEMINI FOOD ANALYSIS
# =========================================================

def analyze_food(
    image_bytes,
    mime_type,
    prompt
):

    # -----------------------------------------------------
    # Try available models one by one.
    # -----------------------------------------------------

    models_to_try = [

        "gemini-3.8-flash",

        "gemini-3.1-flash-lite",

        "gemini-3.5-flash"

    ]

    last_error = None

    for model_name in models_to_try:

        try:

            response = client.models.generate_content(

                model=model_name,

                contents=[

                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type
                    ),

                    prompt

                ]

            )

            if response.text:

                return response.text

            raise Exception(
                "Gemini returned an empty response."
            )

        except Exception as error:

            last_error = error

            error_text = str(error)

            # -------------------------------------------------
            # Try another model for temporary server problems.
            # -------------------------------------------------

            if (
                "503" in error_text
                or
                "UNAVAILABLE" in error_text
                or
                "high demand" in error_text.lower()
            ):

                continue

            # -------------------------------------------------
            # Other errors should be shown immediately.
            # -------------------------------------------------

            raise error

    raise Exception(

        "Gemini is temporarily unavailable. "
        "The available models returned an error.\n\n"
        f"Last error: {last_error}"

    )


# =========================================================
# USER PROFILE
# =========================================================

st.subheader("👤 Your Profile & Details")

col1, col2 = st.columns(2)


with col1:

    dish_name = st.text_input(
        "🍽️ What dish are you uploading?",
        placeholder="e.g. Chicken Biryani"
    )

    weight = st.number_input(
        "⚖️ Weight (kg)",
        min_value=20.0,
        max_value=250.0,
        value=70.0,
        step=0.5
    )

    age = st.number_input(
        "🎂 Age",
        min_value=13,
        max_value=100,
        value=18
    )


with col2:

    height = st.number_input(
        "📏 Height (cm)",
        min_value=100.0,
        max_value=250.0,
        value=170.0,
        step=0.5
    )

    sex = st.selectbox(
        "Sex",
        [
            "Prefer not to say",
            "Male",
            "Female"
        ]
    )

    activity = st.selectbox(
        "🏃 Activity Level",
        [
            "Sedentary",
            "Lightly Active",
            "Moderately Active",
            "Very Active"
        ]
    )


goal = st.selectbox(
    "🎯 Your Goal",
    [
        "Maintain Weight",
        "Lose Weight",
        "Gain Weight"
    ]
)


recipient_email = st.text_input(
    "📧 Your Email Address (optional)",
    placeholder="you@example.com"
)
recipient_whatsapp = st.text_input(
    "📱 Your WhatsApp Number (with country code)",
    placeholder="+91XXXXXXXXXX"
)


# =========================================================
# AUTOMATIC DAILY TARGET CALCULATION
# =========================================================

daily_targets = calculate_daily_targets(
    weight=weight,
    height=height,
    age=age,
    sex=sex,
    activity=activity,
    goal=goal
)


# =========================================================
# DAILY NUTRITION DASHBOARD
# =========================================================
if st.button("🔄 Reset Today's Tracking"):
    st.session_state.meal_history = []
    st.session_state.daily_calories_consumed = 0.0
    st.session_state.daily_protein_consumed = 0.0
    st.success("Today's food tracking has been reset! ✅")
    st.rerun()
st.subheader("📊 Your Daily Nutrition Target")

target_col1, target_col2, target_col3 = st.columns(3)


with target_col1:

    st.metric(
        "🔥 Daily Calories",
        f"{daily_targets['calories']} kcal"
    )


with target_col2:

    st.metric(
        "💪 Daily Protein",
        f"{daily_targets['protein']} g"
    )


with target_col3:

    st.metric(
        "💧 Daily Water",
        f"{daily_targets['water']} L"
    )


st.info(
    "💡 These targets are automatically estimated from "
    "your profile, activity level and selected goal. "
    "They are for project/demo purposes and are not "
    "medical recommendations."
)


st.write("")
# =================================================
# WATER TRACKER
# =================================================

if "water_consumed" not in st.session_state:
    st.session_state.water_consumed = 0.0

st.markdown("### 💧 Water Tracker")

water_amount = st.number_input(
    "Add Water (Litres)",
    min_value=0.1,
    max_value=2.0,
    value=0.5,
    step=0.1
)

if st.button("➕ Add Water"):
    st.session_state.water_consumed += water_amount

water_progress = min(
    st.session_state.water_consumed / daily_targets["water"],
    1.0
)

st.progress(water_progress)

st.write(
    f"💧 {st.session_state.water_consumed:.1f} L / "
    f"{daily_targets['water']:.1f} L"
)

if st.session_state.water_consumed >= daily_targets["water"]:
    st.success("🎉 Daily water target reached!")
else:
    remaining_water = (
        daily_targets["water"]
        - st.session_state.water_consumed
    )

    st.caption(
        f"{remaining_water:.1f} L remaining today"
    )


# =========================================================
# UPLOAD IMAGE
# =========================================================

if "upload_key" not in st.session_state:

    st.session_state.upload_key = 0


uploaded_file = st.file_uploader(

    "📸 Upload a food image",

    type=[
        "jpg",
        "jpeg",
        "png"
    ],

    key=f"food_uploader_{st.session_state.upload_key}"

)


# =========================================================
# IMAGE PREVIEW
# =========================================================

if uploaded_file:

    st.image(
        uploaded_file,
        caption="Your food",
        use_container_width=True
    )

    st.write("")


    # =====================================================
    # ANALYZE BUTTON
    # =====================================================

    analyze = st.button(
        "🔍 Analyze My Food",
        use_container_width=True
    )


    if analyze:

        with st.spinner(
            "🤖 MacroSnap is analyzing your food..."
        ):

            try:

                # -------------------------------------------------
                # READ IMAGE
                # -------------------------------------------------

                image_bytes = uploaded_file.getvalue()


                # -------------------------------------------------
                # PROMPT
                # -------------------------------------------------

                prompt = f"""
You are MacroSnap, an AI food and nutrition assistant.

Analyze the food shown in the uploaded image.

USER INFORMATION

Dish name:
{dish_name if dish_name else "Not specified. Identify the dish from the image."}

Age:
{age}

Weight:
{weight} kg

Height:
{height} cm

Sex:
{sex}

Activity Level:
{activity}

Goal:
{goal}

ESTIMATED DAILY TARGETS

Daily Calories:
{daily_targets['calories']} kcal

Daily Protein:
{daily_targets['protein']} g

Daily Water:
{daily_targets['water']} L

Use the dish name as additional context, but inspect the image yourself.

Estimate the nutrition for the visible serving.

IMPORTANT:

- Nutrition values are estimates.
- Do not claim medical certainty.
- Do not invent ingredients that cannot reasonably be identified.
- Estimate the visible portion.
- Consider the user's selected goal.
- Consider the user's daily calorie and protein targets.
- Give simple and useful guidance.
- Do not diagnose medical conditions.

Return EXACTLY this format:

FOOD: <food name>

SERVING: <estimated visible serving size>

CALORIES: <number> kcal

PROTEIN: <number> g

CARBS: <number> g

FAT: <number> g

DESCRIPTION: <one short sentence describing the food>

RECOMMENDATION: <one short sentence telling the user whether this estimated serving is reasonable for their selected goal>
"""


                # -------------------------------------------------
                # GEMINI
                # -------------------------------------------------

                result = analyze_food(

                    image_bytes,

                    uploaded_file.type,

                    prompt

                )


                # -------------------------------------------------
                # PARSE RESULT
                # -------------------------------------------------

                nutrition = extract_nutrition(result)

                # =================================================
                # SAVE FOOD TO TODAY'S MEAL HISTORY
                # =================================================

                if "meal_history" not in st.session_state:
                    st.session_state.meal_history = []

                st.session_state.meal_history.append({
                    "food": nutrition["food"],
                    "calories": float(nutrition["calories"]) if nutrition["calories"] != "N/A" else 0,
                    "protein": float(nutrition["protein"]) if nutrition["protein"] != "N/A" else 0,
                    "carbs": float(nutrition["carbs"]) if nutrition["carbs"] != "N/A" else 0,
                    "fat": float(nutrition["fat"]) if nutrition["fat"] != "N/A" else 0,
                })


                recommendation = nutrition[
                    "recommendation"
                ]

                if not recommendation:

                    recommendation = (
                        "Use this nutrition estimate "
                        "as a general guide."
                    )

                # =================================================
                # TODAY'S MEAL HISTORY
                # =================================================

                st.markdown("### 🍽️ Today's Meals")

                for i, meal in enumerate(st.session_state.meal_history, 1):

                    st.write(
                        f"**{i}. {meal['food']}** — "
                        f"{meal['calories']:.0f} kcal | "
                        f"{meal['protein']:.0f} g protein"
                    )

                total_calories = sum(
                    meal["calories"]
                    for meal in st.session_state.meal_history
                )

                total_protein = sum(
                    meal["protein"]
                    for meal in st.session_state.meal_history
                )

                # Save the complete report only after today's totals exist.
                # Streamlit reruns the script when Email/WhatsApp is clicked,
                # so these values must persist in session_state.
                st.session_state.last_report = {
                    "nutrition": nutrition,
                    "recommendation": recommendation,
                    "total_calories": total_calories,
                    "total_protein": total_protein,
                    "daily_targets": daily_targets,
                }

                st.info(
                    f"📊 **Today's Total:** "
                    f"{total_calories:.0f} kcal | "
                    f"{total_protein:.0f} g protein"
                )
                # =================================================
                # DAILY PROGRESS DASHBOARD
                # =================================================

                st.markdown("### 📈 Today's Progress")

                calorie_progress = min(
                    total_calories / daily_targets["calories"],
                    1.0
                )

                protein_progress = min(
                    total_protein / daily_targets["protein"],
                    1.0
                )

                progress_col1, progress_col2 = st.columns(2)

                with progress_col1:

                    st.write(
                        f"🔥 **Calories:** "
                        f"{total_calories:.0f} / "
                        f"{daily_targets['calories']} kcal"
                    )

                    st.progress(calorie_progress)

                    st.caption(
                        f"{(total_calories / daily_targets['calories']) * 100:.1f}% of daily target"
                    )

                with progress_col2:

                    st.write(
                        f"💪 **Protein:** "
                        f"{total_protein:.0f} / "
                        f"{daily_targets['protein']} g"
                    )

                    st.progress(protein_progress)

                    st.caption(
                        f"{(total_protein / daily_targets['protein']) * 100:.1f}% of daily target"
                    )

                remaining_calories = max(
                    daily_targets["calories"] - total_calories,
                    0
                )

                remaining_protein = max(
                    daily_targets["protein"] - total_protein,
                    0
                )

                st.success(
                    f"🎯 Remaining today: "
                    f"{remaining_calories:.0f} kcal | "
                    f"{remaining_protein:.0f} g protein"
                )
                # =================================================
                # DAILY SUMMARY
                # =================================================
                if st.button("🔄 Start New Day / Reset Tracking"):
                    st.session_state.meal_history = []
                    st.session_state.daily_calories_consumed = 0.0
                    st.session_state.daily_protein_consumed = 0.0
                    st.success("Today's tracking has been reset! 🎉")
                    st.rerun()
                st.markdown("### 📋 Today's Food Summary")

                if st.session_state.meal_history:

                    for i, meal in enumerate(
                        st.session_state.meal_history,
                        start=1
                    ):
                        st.write(
                            f"**{i}. {meal['food']}**  \n"
                            f"🔥 {meal['calories']:.0f} kcal | "
                            f"💪 {meal['protein']:.1f} g protein | "
                            f"🍚 {meal['carbs']:.1f} g carbs | "
                            f"🥑 {meal['fat']:.1f} g fat"
                        )

                else:

                    st.info("No meals tracked yet today.")

                # =================================================
                # DOWNLOAD DAILY REPORT
                # =================================================

                if st.session_state.meal_history:

                    report_lines = [
                        "MACROSNAP - DAILY NUTRITION REPORT",
                        "",
                        f"Daily Calories Target: {daily_targets['calories']} kcal",
                        f"Daily Protein Target: {daily_targets['protein']} g",
                        f"Daily Water Target: {daily_targets['water']} L",
                        "",
                        "TODAY'S MEALS",
                        "------------------------------"
                    ]

                    for i, meal in enumerate(
                        st.session_state.meal_history,
                        start=1
                    ):
                        report_lines.append(
                            f"{i}. {meal['food']}"
                        )
                        report_lines.append(
                            f"Calories: {meal['calories']:.0f} kcal"
                        )
                        report_lines.append(
                            f"Protein: {meal['protein']:.1f} g"
                        )
                        report_lines.append(
                            f"Carbs: {meal['carbs']:.1f} g"
                        )
                        report_lines.append(
                            f"Fat: {meal['fat']:.1f} g"
                        )
                        report_lines.append("")

                    report_lines.extend([
                        "DAILY TOTAL",
                        "------------------------------",
                        f"Calories: {total_calories:.0f} kcal",
                        f"Protein: {total_protein:.1f} g",
                        "",
                        "Generated by MacroSnap 🥗"
                    ])

                    daily_report = "\n".join(report_lines)

                    st.download_button(
                        "📥 Download Daily Report",
                        daily_report,
                        file_name="macrosnap_daily_report.txt",
                        mime="text/plain",
                        use_container_width=True
                    )    

                # =================================================
                # DAILY PROGRESS
                # =================================================

                st.markdown("### 📈 Today's Progress")

                calorie_progress = min(
                    total_calories / daily_targets["calories"],
                    1.0
                )

                protein_progress = min(
                    total_protein / daily_targets["protein"],
                    1.0
                )

                progress_col1, progress_col2 = st.columns(2)

                with progress_col1:

                    st.write("🔥 Calories")

                    st.progress(calorie_progress)

                    remaining_calories = max(
                        daily_targets["calories"] - total_calories,
                        0
                    )

                    st.caption(
                        f"{remaining_calories:.0f} kcal remaining"
                    )


                with progress_col2:

                    st.write("💪 Protein")

                    st.progress(protein_progress)

                    remaining_protein = max(
                        daily_targets["protein"] - total_protein,
                        0
                    )

                    st.caption(
                        f"{remaining_protein:.0f} g protein remaining"
                    )
                # =================================================
                # SUCCESS MESSAGE
                # =================================================

                st.success(
                    "Analysis complete! 🎉"
                )


                # =================================================
                # FOOD NAME
                # =================================================

                st.subheader(
                    "📊 Nutrition Estimate"
                )

                st.markdown(
                    f"### 🍽️ {nutrition['food']}"
                )

                st.write(
                    f"**Estimated Serving:** "
                    f"{nutrition['serving']}"
                )


                # =================================================
                # NUTRITION METRICS
                # =================================================

                m1, m2, m3, m4 = st.columns(4)


                with m1:

                    st.metric(
                        "🔥 Calories",
                        f"{nutrition['calories']} kcal"
                    )


                with m2:

                    st.metric(
                        "💪 Protein",
                        f"{nutrition['protein']} g"
                    )


                with m3:

                    st.metric(
                        "🍚 Carbs",
                        f"{nutrition['carbs']} g"
                    )


                with m4:

                    st.metric(
                        "🥑 Fat",
                        f"{nutrition['fat']} g"
                    )


                # =================================================
                # DESCRIPTION
                # =================================================

                if nutrition["description"]:

                    st.markdown(
                        "### 📝 Description"
                    )

                    st.write(
                        nutrition["description"]
                    )


                # =================================================
                # DAILY TARGET COMPARISON
                # =================================================

                # =================================================
                # DAILY PROGRESS DASHBOARD
                # =================================================

                st.markdown("### 📈 Today's Progress")

                try:
                    consumed_calories = sum(
                        meal["calories"]
                        for meal in st.session_state.meal_history
                    )

                    consumed_protein = sum(
                        meal["protein"]
                        for meal in st.session_state.meal_history
                    )

                    calorie_target = daily_targets["calories"]
                    protein_target = daily_targets["protein"]

                    calorie_progress = min(
                        consumed_calories / calorie_target,
                        1.0
                    )

                    protein_progress = min(
                        consumed_protein / protein_target,
                        1.0
                    )

                    progress_col1, progress_col2 = st.columns(2)

                    with progress_col1:
                        st.metric(
                            "🔥 Calories",
                            f"{consumed_calories:.0f} / {calorie_target} kcal"
                        )

                        st.progress(calorie_progress)

                        st.caption(
                            f"{(consumed_calories / calorie_target) * 100:.1f}% of daily target"
                        )

                    with progress_col2:
                        st.metric(
                            "💪 Protein",
                            f"{consumed_protein:.1f} / {protein_target} g"
                        )

                        st.progress(protein_progress)

                        st.caption(
                            f"{(consumed_protein / protein_target) * 100:.1f}% of daily target"
                        )

                except (ValueError, TypeError, ZeroDivisionError):
                    st.info("Daily progress is unavailable.")


                st.markdown(
                    "### 🎯 Daily Target Comparison"
                )


                # -------------------------------------------------
                # Convert nutrition values to numbers
                # -------------------------------------------------

                try:

                    food_calories = float(
                        nutrition["calories"]
                    )

                    food_protein = float(
                        nutrition["protein"]
                    )

                    daily_calorie_target = float(
                        daily_targets["calories"]
                    )

                    daily_protein_target = float(
                        daily_targets["protein"]
                    )

                    calorie_percentage = (
                        food_calories
                        /
                        daily_calorie_target
                    ) * 100

                    protein_percentage = (
                        food_protein
                        /
                        daily_protein_target
                    ) * 100

                    calorie_percentage = min(
                        calorie_percentage,
                        100
                    )

                    protein_percentage = min(
                        protein_percentage,
                        100
                    )


                    comparison_col1, comparison_col2 = st.columns(2)


                    with comparison_col1:

                        st.metric(
                            "🔥 Calories Used",
                            f"{food_calories:.0f} / "
                            f"{daily_calorie_target:.0f} kcal"
                        )

                        st.progress(
                            calorie_percentage / 100
                        )

                        st.caption(
                            f"{calorie_percentage:.1f}% "
                            "of estimated daily calories"
                        )


                    with comparison_col2:

                        st.metric(
                            "💪 Protein Used",
                            f"{food_protein:.1f} / "
                            f"{daily_protein_target:.0f} g"
                        )

                        st.progress(
                            protein_percentage / 100
                        )

                        st.caption(
                            f"{protein_percentage:.1f}% "
                            "of estimated daily protein"
                        )


                    # -------------------------------------------------
                    # Portion Guidance
                    # -------------------------------------------------

                    st.markdown(
                        "### 🍽️ Portion Guidance"
                    )


                    if calorie_percentage <= 20:

                        portion_message = (
                            "This serving represents a relatively "
                            "small portion of your estimated daily "
                            "calorie target."
                        )

                    elif calorie_percentage <= 35:

                        portion_message = (
                            "This serving represents a moderate "
                            "portion of your estimated daily "
                            "calorie target."
                        )

                    elif calorie_percentage <= 50:

                        portion_message = (
                            "This serving represents a substantial "
                            "portion of your estimated daily "
                            "calorie target."
                        )

                    else:

                        portion_message = (
                            "This serving represents a large portion "
                            "of your estimated daily calorie target."
                        )


                    st.info(
                        portion_message
                    )


                except (
                    ValueError,
                    TypeError
                ):

                    st.warning(
                        "Daily target comparison is unavailable "
                        "because the AI returned non-numeric "
                        "nutrition values."
                    )


                # =================================================
                # RECOMMENDATION
                # =================================================

                st.markdown(
                    "### 🎯 Recommendation"
                )

                st.info(
                    recommendation
                )


                # =================================================
                # MACRO CHART
                # =================================================

                st.markdown(
                    "### 📊 Macro Breakdown"
                )


                try:

                    macro_data = pd.DataFrame({

                        "Macro": [
                            "Protein",
                            "Carbs",
                            "Fat"
                        ],

                        "Grams": [

                            float(
                                nutrition["protein"]
                            ),

                            float(
                                nutrition["carbs"]
                            ),

                            float(
                                nutrition["fat"]
                            )

                        ]

                    })


                    st.bar_chart(
                        macro_data.set_index(
                            "Macro"
                        )
                    )


                except (
                    ValueError,
                    TypeError
                ):

                    st.info(
                        "Macro chart is unavailable "
                        "for this result."
                    )


                # =================================================
                # USER PROFILE SUMMARY
                # =================================================

                st.markdown(
                    "### 👤 Your Profile"
                )


                profile_col1, profile_col2 = st.columns(2)


                with profile_col1:

                    st.write(
                        f"**Weight:** {weight} kg"
                    )

                    st.write(
                        f"**Height:** {height} cm"
                    )

                    st.write(
                        f"**Age:** {age}"
                    )


                with profile_col2:

                    st.write(
                        f"**Activity:** {activity}"
                    )

                    st.write(
                        f"**Goal:** {goal}"
                    )

                    st.write(
                        f"**Sex:** {sex}"
                    )


                # =================================================
                # DAILY TARGET SUMMARY
                # =================================================

                st.markdown(
                    "### 📅 Your Estimated Daily Targets"
                )


                target_summary_col1, target_summary_col2, target_summary_col3 = st.columns(3)


                with target_summary_col1:

                    st.metric(
                        "🔥 Calories",
                        f"{daily_targets['calories']} kcal"
                    )


                with target_summary_col2:

                    st.metric(
                        "💪 Protein",
                        f"{daily_targets['protein']} g"
                    )


                with target_summary_col3:

                    st.metric(
                        "💧 Water",
                        f"{daily_targets['water']} L"
                    )


                # =================================================
                # WARNING
                # =================================================

                st.caption(
                    "⚠️ Nutrition values and daily targets are "
                    "AI/project-based estimates and may not "
                    "represent exact nutritional requirements. "
                    "For medical or dietary conditions, consult "
                    "a qualified healthcare professional."
                )


                # Sending is handled by the persistent controls at the bottom of the app.

            # =====================================================
            # ERROR HANDLING
            # =====================================================

            except Exception as error:

                error_text = str(error)


                if (
                    "503" in error_text
                    or
                    "UNAVAILABLE" in error_text
                    or
                    "high demand" in error_text.lower()
                ):

                    st.error(
                        "⚠️ Gemini is temporarily busy."
                    )

                    st.info(
                        "Please wait a few seconds and "
                        "click Analyze My Food again."
                    )

                    st.caption(
                        "MacroSnap automatically tried "
                        "the available fallback models."
                    )


                else:

                    st.error(
                        "Something went wrong during analysis."
                    )

                    st.code(
                        error_text
                    )


# =========================================================
# NO IMAGE
# =========================================================

else:

    st.info(
        "👆 Upload a photo of your food to get started."
    )

# =========================================================
# PERSISTENT SEND ACTIONS
# =========================================================

if "last_report" in st.session_state:

    report = st.session_state.last_report
    nutrition = report["nutrition"]
    recommendation = report["recommendation"]
    total_calories = report["total_calories"]
    total_protein = report["total_protein"]
    daily_targets = report["daily_targets"]

    st.markdown("---")
    st.subheader("📤 Share Your MacroSnap Report")

    send_col1, send_col2 = st.columns(2)

    with send_col1:
        if st.button("📧 Send to Email", use_container_width=True, key="send_email_final"):
            if not recipient_email.strip():
                st.warning("Enter your email address above first.")
            else:
                email_body = f"""MACROSNAP - DAILY NUTRITION REPORT

Daily Calories Target: {daily_targets['calories']} kcal
Daily Protein Target: {daily_targets['protein']} g
Daily Water Target: {daily_targets['water']} L

TODAY'S FOOD
------------------------------
{nutrition['food']}
Calories: {nutrition['calories']} kcal
Protein: {nutrition['protein']} g
Carbs: {nutrition['carbs']} g
Fat: {nutrition['fat']} g

DAILY TOTAL
------------------------------
Calories: {total_calories:.0f} kcal
Protein: {total_protein:.1f} g

RECOMMENDATION
------------------------------
{recommendation}

Generated by MacroSnap 🥗
"""
                try:
                    send_email(
                        recipient_email.strip(),
                        "Your MacroSnap Daily Nutrition Report 🥗",
                        email_body
                    )
                    st.success("📧 Email sent successfully!")
                except Exception as e:
                    st.error("❌ Email failed.")
                    st.code(str(e))

    with send_col2:
        if st.button("📲 Send to WhatsApp", use_container_width=True, key="send_whatsapp_final"):
            if not recipient_whatsapp.strip():
                st.warning("Enter your WhatsApp number above first.")
            else:
                whatsapp_body = f"""🥗 MacroSnap Daily Summary

🍽️ Food: {nutrition['food']}
⚖️ Serving: {nutrition['serving']}

🔥 Calories: {nutrition['calories']} kcal
💪 Protein: {nutrition['protein']} g
🍚 Carbs: {nutrition['carbs']} g
🥑 Fat: {nutrition['fat']} g

🎯 Daily Targets
Calories: {daily_targets['calories']} kcal
Protein: {daily_targets['protein']} g
Water: {daily_targets['water']} L

📊 Today's Total
Calories: {total_calories:.0f} kcal
Protein: {total_protein:.1f} g

🎯 Recommendation
{recommendation}

Keep going with your goal! 🚀
— MacroSnap 🥗
"""
                try:
                    sid = send_whatsapp(
                        recipient_whatsapp.strip(),
                        whatsapp_body
                    )
                    st.success(f"📲 WhatsApp message sent! Message ID: {sid}")
                except Exception as e:
                    st.error("❌ WhatsApp failed.")
                    st.code(str(e))

    if st.button("📷 Analyze Another Food", use_container_width=True, key="analyze_another_final"):
        st.session_state.upload_key += 1
        st.session_state.pop("last_report", None)
        st.rerun()

