import streamlit as st
import pdfplumber
import re
import pandas as pd



username = st.secrets["credentials"]["username"]
password = st.secrets["credentials"]["password"]

# Create session state vars if not exist
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Login form if not authenticated
if not st.session_state.authenticated:
    st.title("Login Required")

    username = st.text_input("Enter User ID")
    password = st.text_input("Enter Password", type="password")
    login_button = st.button("Login")

    if login_button:
        if username == CORRECT_USERNAME and password == CORRECT_PASSWORD:
            st.session_state.authenticated = True
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid credentials. Try again.")

    st.stop()

st.title("PDF Product Code & Price Extractor")

# Selection option
option = st.radio(
    "Choose parsing mode:",
    ("Parse file **with discount**", "Parse file **without discount**")
)

# File uploader
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# Regex patterns
code_pattern = re.compile(r'[A][A-D0-9]\d{5}\b')
price_pattern = re.compile(r'(€|CHF)\s?\d{1,4}(?:\.\d{3})*,(\d{2}|\-)')


def is_page_number(text):
    return re.match(r'^\d{1,2}$', text) is not None


def extract_page_number(page):
    words = page.extract_words()
    bottom_threshold = page.height - 30
    bottom_words = [w for w in words if w['top'] > bottom_threshold]

    left_margin_max = 55
    right_margin_min = page.width - 60

    for w in bottom_words:
        if w['x1'] < left_margin_max and is_page_number(w['text']):
            return w['text']
    for w in bottom_words:
        if w['x0'] > right_margin_min and is_page_number(w['text']):
            return w['text']
    return None


if uploaded_file:
    extracted_data = []
    all_codes=[]

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            page_number = extract_page_number(page)

            matches = []
            for m in code_pattern.finditer(text):
                matches.append({'type': 'code', 'value': m.group(), 'start': m.start()})
            for m in price_pattern.finditer(text):
                matches.append({'type': 'price', 'value': m.group(), 'start': m.start()})

            matches.sort(key=lambda x: x['start'])
            buffer_codes = []

            if option == "Parse file **without discount**":
                for item in matches:
                    if item['type'] == 'code':
                        buffer_codes.append(item['value'])
                        all_codes.append((page_number, item['value']))

                    elif item['type'] == 'price':
                   
                        for code in buffer_codes:
                            extracted_data.append({
                                'Page Number': page_number,
                                'Code': code,
                                'Price': item['value']
                            })
                        buffer_codes = []

                # Handle any leftover codes without price
                for code in buffer_codes:
                    extracted_data.append({
                        'Page Number': page_number,
                        'Code': code,
                        'Price': None
                    })

            else:  # with discount
                i = 0
                while i < len(matches):

                    item = matches[i]

                    if item['type'] == 'code':
                        buffer_codes.append(item['value'])
                        all_codes.append((page_number, item['value']))
                        i += 1

                    elif item['type'] == 'price':
                        temp_price = item['value']
                        next_item = matches[i + 1] if (i + 1) < len(matches) else None

                        if next_item and next_item['type'] == 'price':
                            # Discount detected
                            discount_price = next_item['value']

                            for code in buffer_codes:
                                extracted_data.append({
                                    'Page Number': page_number,
                                    'Code': code,
                                    'PV': temp_price,
                                    'PV Promo': discount_price
                                })
                            buffer_codes = []
                            i += 2  # skip both prices
                        else:
                            # Only one price, no discount
                            for code in buffer_codes:
                                extracted_data.append({
                                    'Page Number': page_number,
                                    'Code': code,
                                    'PV': temp_price,
                                    'PV Promo': None
                                })
                            buffer_codes = []
                            i += 1

                # Leftover codes with no prices
                for code in buffer_codes:
                    extracted_data.append({
                        'Page Number': page_number,
                        'Code': code,
                        'PV': None,
                        'PV Promo': None
                    })

    # Create DataFrame after all pages are processed
    df = pd.DataFrame(extracted_data)

    # Format cleanup
    if option == "Parse file **without discount**":
        df["Price"] = df["Price"].str.replace(r"(€|CHF)\s?", "", regex=True).str.strip()
        df["Price"] = df["Price"].str.replace(".", "", regex=False).str.strip()
        df["Price"] = df["Price"].str.replace(",", ".", regex=False).str.strip()
        df["Price"] = df["Price"].str.replace("-", "00", regex=False).str.strip()
        df["Price"] = pd.to_numeric(df["Price"], errors='coerce')
    else:
        for col in ['PV', 'PV Promo']:
            df[col] = df[col].astype(str)
            df[col] = df[col].str.replace(r"(€|CHF)\s?", "", regex=True).str.strip()
            df[col] = df[col].str.replace(".", "", regex=False).str.strip()
            df[col] = df[col].str.replace(",", ".", regex=False).str.strip()
            df[col] = df[col].str.replace("-", "00", regex=False).str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Show results
    st.success("Parsing complete!")
    st.dataframe(df)

    # CSV download
    filename = "parsed_discount.csv" if "with discount" in option else "parsed_nodiscount.csv"
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV", csv, filename, "text/csv")
