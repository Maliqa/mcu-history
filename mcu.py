import streamlit as st
import pandas as pd
import sqlite3
import os
import base64
import logging
from datetime import datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


st.set_page_config(
    page_title="MCU CITSECH",
    page_icon="🏥",
    layout="centered"
)

os.makedirs("database/uploads", exist_ok=True)

# =========================================
# ==== AUTO INCLUDE CUSTOM CSS LEBAR BOX ===
# =========================================
st.markdown("""
    <style>
    .block-container {
        max-width: 1200px !important;
        padding-left: 48px !important;
        padding-right: 48px !important;
    }
    .streamlit-expander {
        max-width: 700px !important;
    }
    .stFileUploader {
        width: 320px !important;
    }
    </style>
""", unsafe_allow_html=True)

LOG_FILE = "database/app.log"
os.makedirs("database", exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# ======== SETTING REPO GITHUB UNTUK LINK MCU PDF =========
GITHUB_OWNER = "Maliqa"
GITHUB_REPO = "mcu-history"
GITHUB_BRANCH = "main"

# ============== Utilities (safe rerun etc.) ==============
def safe_rerun():
    """
    Try to rerun the Streamlit app in a way compatible with multiple versions.
    If rerun isn't available, reload the browser page via JS (best-effort).
    """
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        elif hasattr(st, "rerun"):
            st.rerun()
        else:
            # Fallback: force browser reload
            st.markdown("<script>window.location.reload()</script>", unsafe_allow_html=True)
            st.stop()
    except Exception:
        # Final fallback
        st.markdown("<script>window.location.reload()</script>", unsafe_allow_html=True)
        st.stop()

# ============== LOGIN FORM ==============
def login_form():
    """
    Display login form and set session_state['logged_in'] on success.
    If not logged in, stop execution so the rest of the app is hidden.
    """
    logo_path = "cistech.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=280)
    else:
        st.markdown("<h3>MCU Dashboard</h3>", unsafe_allow_html=True)

    st.markdown("<h3 style='text-align:center;margin-top:0.25rem;'>Login MCU Dashboard</h3>", unsafe_allow_html=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_btn = st.button("Login")
    if login_btn:
        allowed = {"MAA":"MAA","SZA":"SZA","EWS":"EWS"}
        if username and username.upper() in allowed and password == allowed[username.upper()]:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username.upper()
            st.success(f"Login success! Welcome, {username.upper()}")
            # Rerun so the rest of the app shows immediately
            safe_rerun()
            return
        else:
            st.error("Username or password salah!")
    # If user reaches here and not logged in, stop so the app doesn't render
    st.stop()

# Initialize logged_in key if missing (prevents KeyError on refresh)
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state.get("logged_in", False):
    login_form()

# If we reach here, user is logged in
def show_logo():
    logo_path = "cistech.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=500)

def init_db():
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nik TEXT UNIQUE,
            employee_name TEXT,
            birth_date TEXT,
            position TEXT,
            hire_date TEXT,
            work_period TEXT,
            mcu_date TEXT,
            mcu_expired TEXT,
            file_mcu_main TEXT,
            examination_result TEXT,
            diagnosis TEXT,
            recommendation TEXT,
            status TEXT,
            email TEXT,
            reminder_sent INTEGER DEFAULT 0
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS mcu_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nik TEXT,
            mcu_year INTEGER,
            mcu_date TEXT,
            expired_date TEXT,
            file_name TEXT,
            diagnosis TEXT,
            recommendation TEXT
        )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error initializing DB: {e}")

init_db()

def calculate_work_period(hire_date):
    if pd.isna(hire_date):
        return "0 year"
    hire_date = pd.to_datetime(hire_date)
    now = datetime.now()
    delta = now - hire_date
    years = delta.days // 365
    months = (delta.days % 365) // 30
    return f"{years} year(s) {months} month(s)"

def calculate_mcu_expiry(mcu_date):
    if pd.isna(mcu_date):
        return None
    mcu_date = pd.to_datetime(mcu_date)
    return mcu_date + timedelta(days=365)

def check_mcu_status(mcu_expired):
    if pd.isna(mcu_expired):
        return "No MCU"
    mcu_expired = pd.to_datetime(mcu_expired)
    if datetime.now() > mcu_expired:
        return "Expired"
    elif (mcu_expired - datetime.now()).days <= 30:
        return "Will Expire"
    else:
        return "Active"

def save_uploaded_file(uploaded_file, nik, year):
    """
    Save uploaded file locally. Returns file_name on success.
    """
    if uploaded_file is not None:
        try:
            # streamlit UploadedFile has getbuffer()
            data = uploaded_file.getbuffer()
        except Exception:
            try:
                uploaded_file.seek(0)
                data = uploaded_file.read()
            except Exception:
                data = None
        if data is None:
            st.error("Invalid file uploaded.")
            return None

        if len(data) > 100 * 1024 * 1024:
            st.error("❌ Max file size 100 MB!")
            logging.warning("File upload failed: file > 100MB")
            return None

        file_ext = os.path.splitext(uploaded_file.name)[1]
        if not file_ext:
            file_ext = ".pdf"
        file_name = f"{year}{file_ext}"
        file_dir = f"database/uploads/mcu_history/{nik}/"
        os.makedirs(file_dir, exist_ok=True)
        file_path = os.path.join(file_dir, file_name)
        try:
            with open(file_path, "wb") as f:
                f.write(data)
            logging.info(f"Saved uploaded file to {file_path}")
            return file_name
        except Exception as e:
            st.error("❌ Failed to save file!")
            logging.error(f"File upload error: {e}")
            return None
    return None

def get_file_path_mcu_history(nik, file_name):
    if file_name:
        return os.path.join(f"database/uploads/mcu_history/{nik}/", file_name)
    return None

def get_file_path(filename):
    if filename:
        return os.path.join("database/uploads", filename)
    return None

def validate_dates(birth_date, hire_date, mcu_date):
    # implement validation if needed, return error string or None
    return None

def get_github_mcu_url(nik, file_name):
    return f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/blob/{GITHUB_BRANCH}/mcu_files/{nik}/{file_name}?raw=true"

def get_mcu_history_db(nik):
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        df = pd.read_sql("SELECT * FROM mcu_history WHERE nik=? ORDER BY mcu_year DESC", conn, params=(nik,))
        conn.close()
        return df
    except Exception as e:
        logging.error(f"Error get MCU history: {e}")
        return pd.DataFrame()

def add_mcu_history(nik, mcu_year, mcu_date, expired_date, file_name, diagnosis, recommendation):
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO mcu_history (nik, mcu_year, mcu_date, expired_date, file_name, diagnosis, recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nik, mcu_year, mcu_date, expired_date, file_name, diagnosis, recommendation))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error add MCU history: {e}")
        return False

def edit_employee(nik, data):
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE employee SET
            employee_name=?,
            birth_date=?,
            position=?,
            hire_date=?,
            work_period=?,
            mcu_date=?,
            mcu_expired=?,
            file_mcu_main=?,
            examination_result=?,
            diagnosis=?,
            recommendation=?,
            status=?,
            email=?
        WHERE nik=?
        ''', (
            data['employee_name'],
            data['birth_date'],
            data['position'],
            data['hire_date'],
            data['work_period'],
            data['mcu_date'],
            data['mcu_expired'],
            data['file_mcu_main'],
            data['examination_result'],
            data['diagnosis'],
            data['recommendation'],
            data['status'],
            data['email'],
            nik
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error edit employee: {e}")
        return False

def delete_employee(nik):
    """
    Delete employee record, related mcu_history rows, and files on disk.
    Return True if deletion was performed.
    """
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employee WHERE nik=?", (nik,))
        cursor.execute("DELETE FROM mcu_history WHERE nik=?", (nik,))
        conn.commit()
        conn.close()

        # Delete files on disk (if any)
        file_dir = os.path.join("database", "uploads", "mcu_history", str(nik))
        if os.path.exists(file_dir):
            for fname in os.listdir(file_dir):
                try:
                    os.remove(os.path.join(file_dir, fname))
                except Exception as e:
                    logging.warning(f"Failed to remove file {fname}: {e}")
            # try to remove directory
            try:
                os.rmdir(file_dir)
            except Exception:
                pass

        logging.info(f"Employee {nik} deleted from DB and disk")
        return True
    except Exception as e:
        logging.error(f"Error delete employee: {e}")
        return False

def delete_mcu_history_file_and_db(nik, file_name, mcu_id):
    """
    Delete a single MCU history row and the associated file on disk.
    """
    file_path = get_file_path_mcu_history(nik, file_name)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            st.error("Gagal delete file fisik!")
            logging.error(f"Failed to remove file {file_path}: {e}")
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        conn.execute("DELETE FROM mcu_history WHERE id=?", (mcu_id,))
        conn.commit()
        conn.close()
        st.success("MCU file berhasil dihapus!")
        # refresh display
        safe_rerun()
    except Exception as e:
        st.error("Gagal delete data dari database!")
        logging.error(f"Failed to delete mcu_history id {mcu_id}: {e}")

def preview_pdf_iframe(file_path, width=700, height=900):
    try:
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="{width}" height="{height}" type="application/pdf" style="border: none;"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Gagal menampilkan PDF: {e}")

# ======== EMAIL REMINDER FUNCTION =========
def send_reminder_email(to_email, employee_name, expired_date, mcu_year):
    # Ganti dengan email dan pass sesuai server perusahaan
    from_email = "shafira.zahara@ptcai.com"
    from_pass = "C!$7ecH_sZAnEW2025"
    subject = f"MCU Expired Reminder - {employee_name}"
    body = f"""
    Dear {employee_name},

    Your MCU (Medical Check Up) for year {mcu_year} will expire on {expired_date}.
    Please update your MCU soon.

    Regards,
    HSE CISTECH
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('mail.ptcai.com', 955)
        server.starttls()
        server.login(from_email, from_pass)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        return True
    except Exception as e:
        logging.error(f"Email send failed to {to_email}: {e}")
        return False

# ----------------- UI / Navigation -----------------
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Choose Page",
    ("Dashboard MCU", "Input MCU Data", "MCU History", "Health Monitoring", "Export MCU Excel")
)

if st.sidebar.button("Logout"):
    # Clear session state and rerun
    for k in list(st.session_state.keys()):
        st.session_state.pop(k, None)
    st.session_state["logged_in"] = False
    st.success("Logged out.")
    safe_rerun()

if page == "Dashboard MCU":
    show_logo()
    st.title("🏥 Employee MCU Dashboard")
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        df = pd.read_sql("SELECT * FROM employee", conn)
        conn.close()
    except Exception as e:
        st.error("Failed to load data!")
        logging.error(f"Dashboard error: {e}")
        df = pd.DataFrame()
    if not df.empty:
        st.header("Employee MCU Status")
        col1, col2, col3, col4 = st.columns(4)
        total_emp = len(df)
        active_mcu = sum(df['status'] == "Active")
        expired_mcu = sum(df['status'] == "Expired")
        will_expired = sum(df['status'] == "Will Expire")
        col1.metric("Total Employee", total_emp)
        col2.metric("MCU Active", active_mcu)
        col3.metric("MCU Expired", expired_mcu)
        col4.metric("Will Expire", will_expired)
        st.header("Health Statistics (Pie Chart)")
        if 'diagnosis' in df.columns and not df['diagnosis'].isna().all():
            diagnosis_counts = df['diagnosis'].value_counts().head(5)
            fig, ax = plt.subplots(figsize=(3.5, 3.5))
            diagnosis_counts.plot(
                kind='pie',
                autopct='%1.1f%%',
                startangle=90,
                shadow=True,
                colors=['#ff9999','#66b3ff','#99ff99','#ffcc99','#c2c2f0'],
                ax=ax
            )
            ax.set_title('Top 5 Health Diagnosis', pad=12)
            ax.set_ylabel('')
            st.pyplot(fig)
            st.write("Diagnosis Details:")
            for i, (diagnosis, jumlah) in enumerate(diagnosis_counts.items(), start=1):
                st.markdown(f"<b>{i}. {diagnosis}</b>: {jumlah} employee", unsafe_allow_html=True)
        else:
            st.warning("Diagnosis data not available.")
        st.header("MCU Reminder")
        try:
            conn = sqlite3.connect("database/mcu_database.db")
            df_db = pd.read_sql("SELECT * FROM employee", conn)
        except Exception as e:
            st.error("Failed to load data for reminder!")
            logging.error(f"Reminder DB error: {e}")
            df_db = pd.DataFrame()
        upcoming = df_db[df_db['status'] == "Will Expire"] if not df_db.empty and 'status' in df_db.columns else pd.DataFrame()
        if not upcoming.empty:
            st.warning(f"⚠️ {len(upcoming)} employee MCU will expire soon!")
            for idx, row in upcoming.iterrows():
                st.write(f"- {row['nik']} | {row['employee_name']} | Expired: {row['mcu_expired']} | Email: {row['email']}")
                if row.get("reminder_sent", 0) != 1 and pd.notna(row["email"]) and row["email"]:
                    email_sent = send_reminder_email(
                        row['email'],
                        row['employee_name'],
                        row['mcu_expired'],
                        pd.to_datetime(row['mcu_date']).year if pd.notna(row['mcu_date']) else ""
                    )
                    if email_sent:
                        st.success(f"Reminder sent to {row['email']}")
                        try:
                            conn2 = sqlite3.connect("database/mcu_database.db")
                            c2 = conn2.cursor()
                            c2.execute("UPDATE employee SET reminder_sent=1 WHERE nik=?", (row['nik'],))
                            conn2.commit()
                            conn2.close()
                        except Exception as e:
                            logging.error(f"Failed to update reminder_sent for {row['nik']}: {e}")
                    else:
                        st.error(f"Failed to send email to {row['email']}")
        else:
            st.success("✅ No MCU will expire soon.")
    else:
        st.warning("Database is empty. Please input MCU data first.")

elif page == "Input MCU Data":
    show_logo()
    st.title("📝 Input MCU Data Employee")
    try:
        with st.form("mcu_form"):
            col1, col2 = st.columns(2)
            with col1:
                nik = st.text_input("NIK", max_chars=20)
                employee_name = st.text_input("Employee Name")
                birth_date = st.date_input("Birth Date", min_value=datetime(1945, 1, 1), max_value=datetime(3000, 12, 31))
                position = st.text_input("Position")
                email = st.text_input("Employee Email")
            with col2:
                hire_date = st.date_input("Hire Date", min_value=datetime(1945, 1, 1), max_value=datetime(3000, 12, 31))
                mcu_date = st.date_input("Last MCU Date", min_value=datetime(1945, 1, 1), max_value=datetime(3000, 12, 31))
                work_period = st.text_input("Work Period (auto)", value=calculate_work_period(hire_date), disabled=True)
                mcu_expired = st.text_input("MCU Expired (auto)", value=calculate_mcu_expiry(mcu_date).strftime("%Y-%m-%d") if mcu_date else "", disabled=True)
            examination_result = st.text_area("Examination Result")
            diagnosis = st.text_input("Diagnosis")
            recommendation = st.text_area("Recommendation")
            file_mcu_main = st.file_uploader("Upload Main MCU Result (PDF/Image)", type=['pdf', 'png', 'jpg', 'jpeg'])
            submitted = st.form_submit_button("Save MCU Data")
            valid_date = True
            error_date = validate_dates(birth_date, hire_date, mcu_date)
            if error_date:
                st.error(error_date)
                valid_date = False
            if submitted and valid_date:
                if not nik or not employee_name:
                    st.error("❌ NIK and Employee Name are required!")
                else:
                    try:
                        conn = sqlite3.connect("database/mcu_database.db")
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM employee WHERE nik=?", (nik,))
                        if cursor.fetchone()[0] > 0:
                            st.error("❌ NIK already registered! Please use another NIK or edit existing data.")
                        else:
                            saved_filename = save_uploaded_file(file_mcu_main, nik, pd.to_datetime(mcu_date).year)
                            cursor.execute('''
                            INSERT INTO employee (
                                nik, employee_name, birth_date, position,
                                hire_date, work_period, mcu_date, mcu_expired,
                                file_mcu_main, examination_result, diagnosis,
                                recommendation, status, email, reminder_sent
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                nik,
                                employee_name,
                                birth_date.strftime("%Y-%m-%d"),
                                position,
                                hire_date.strftime("%Y-%m-%d"),
                                calculate_work_period(hire_date),
                                mcu_date.strftime("%Y-%m-%d") if mcu_date else None,
                                calculate_mcu_expiry(mcu_date).strftime("%Y-%m-%d") if mcu_date else None,
                                saved_filename,
                                examination_result,
                                diagnosis,
                                recommendation,
                                check_mcu_status(calculate_mcu_expiry(mcu_date)) if mcu_date else "No MCU",
                                email,
                                0
                            ))
                            conn.commit()
                            if saved_filename:
                                add_mcu_history(
                                    nik,
                                    pd.to_datetime(mcu_date).year,
                                    mcu_date.strftime("%Y-%m-%d"),
                                    calculate_mcu_expiry(mcu_date).strftime("%Y-%m-%d"),
                                    saved_filename,
                                    diagnosis,
                                    recommendation
                                )
                            st.success("✅ MCU data saved!")
                        conn.close()
                    except Exception as e:
                        st.error("Failed to input data!")
                        logging.error(f"Input MCU error: {e}")
    except Exception as e:
        st.error("Form input error!")
        logging.error(f"Form input error: {e}")

elif page == "MCU History":
    show_logo()
    st.title("📋 Employee MCU History")
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        df = pd.read_sql("SELECT * FROM employee", conn)
        conn.close()
    except Exception as e:
        st.error("Failed to load data!")
        logging.error(f"History error: {e}")
        df = pd.DataFrame()
    
    if not df.empty:
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_query = st.text_input("🔍 Search by NIK or Employee Name")
        
        if search_query:
            filtered_data = df[
                df['nik'].str.contains(search_query, case=False, na=False) | 
                df['employee_name'].str.contains(search_query, case=False, na=False)
            ]
        else:
            filtered_data = df
        
        if not filtered_data.empty:
            selected_employee = st.selectbox(
                "Choose Employee",
                options=filtered_data['employee_name'] + " (" + filtered_data['nik'] + ")",
                format_func=lambda x: x
            )
            
            selected_nik = selected_employee.split("(")[1].replace(")", "")
            employee_data = filtered_data[filtered_data['nik'] == selected_nik].iloc[0]
            
            st.subheader("Employee Information")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**NIK:** {employee_data['nik']}")
                st.write(f"**Name:** {employee_data['employee_name']}")
                st.write(f"**Birth Date:** {employee_data['birth_date']}")
            with col2:
                st.write(f"**Position:** {employee_data['position']}")
                st.write(f"**Hire Date:** {employee_data['hire_date']}")
                st.write(f"**Work Period:** {employee_data['work_period']}")
            with col3:
                st.write(f"**MCU Date:** {employee_data['mcu_date']}")
                st.write(f"**MCU Expired:** {employee_data['mcu_expired']}")
                status = employee_data['status']
                color = "green" if status == "Active" else "orange" if status == "Will Expire" else "red"
                st.write(f"**Status:** <span style='color:{color};font-weight:bold'>{status}</span>", unsafe_allow_html=True)
            
            st.subheader("Examination Result")
            st.write(employee_data['examination_result'])
            
            st.subheader("Diagnosis & Recommendation")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Diagnosis:**")
                st.write(employee_data['diagnosis'])
            with col2:
                st.write(f"**Recommendation:**")
                st.write(employee_data['recommendation'])
            
            st.subheader("Employee MCU History (Expander per record)")
            history_df = get_mcu_history_db(employee_data['nik'])
            
            if not history_df.empty:
                # iterate and show each history item as an expander
                for _, row in history_df.iterrows():
                    exp_key = f"exp_{row['id']}"
                    with st.expander(f"MCU Year: {row['mcu_year']}  —  Date: {row['mcu_date']}", expanded=False):
                        st.write(f"Expired: {row['expired_date']}")
                        st.write(f"Diagnosis: {row['diagnosis']}")
                        st.write(f"Recommendation: {row['recommendation']}")
                        
                        file_name = row['file_name']
                        file_path = get_file_path_mcu_history(employee_data['nik'], file_name)
                        github_url = get_github_mcu_url(employee_data['nik'], file_name)
                        
                        # Action buttons in a row
                        c1, c2, c3 = st.columns([1,1,1])
                        with c1:
                            view_key = f"view_{row['id']}"
                            view_clicked = st.button("View File", key=view_key)
                        with c2:
                            download_key = f"download_{row['id']}"
                            if file_path and os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    file_bytes = f.read()
                                st.download_button(label="⬇️ Download", data=file_bytes, file_name=file_name, mime="application/octet-stream", key=download_key)
                            else:
                                # if not local, provide GitHub link
                                st.markdown(f'<a href="{github_url}" target="_blank" style="text-decoration:none;">⬇️ Download (GitHub)</a>', unsafe_allow_html=True)
                        with c3:
                            del_key = f"delete_{row['id']}"
                            if st.button("🗑️ Delete", key=del_key):
                                confirm_key = f"confirm_delete_{row['id']}"
                                # set a session flag to request confirmation
                                st.session_state[confirm_key] = st.session_state.get(confirm_key, False) or False
                                if not st.session_state.get(confirm_key):
                                    st.session_state[confirm_key] = True
                                    st.warning("Klik lagi untuk konfirmasi penghapusan MCU ini.")
                                else:
                                    delete_mcu_history_file_and_db(employee_data['nik'], file_name, row['id'])
                                    # clear confirm flag
                                    st.session_state.pop(confirm_key, None)
                                    # safe_rerun called inside delete function

                        # If view button clicked, show preview inline (iframe for pdf, st.image for images)
                        if view_clicked:
                            if file_path and os.path.exists(file_path):
                                ext = file_name.split('.')[-1].lower()
                                if ext == 'pdf':
                                    preview_pdf_iframe(file_path, width=800, height=900)
                                else:
                                    try:
                                        st.image(file_path, caption=f"{file_name}", use_column_width=True)
                                    except Exception as e:
                                        st.error(f"Gagal menampilkan image: {e}")
                            else:
                                # no local file: open GitHub raw link in new tab via markdown link and show message
                                st.markdown(f'<a href="{github_url}" target="_blank">📄 Open file on GitHub (raw)</a>', unsafe_allow_html=True)
                                st.info("File tidak ditemukan di server; membuka di GitHub.")
            else:
                st.info("Belum ada histori MCU.")
            
            st.markdown("---")
            # Form untuk menambah MCU baru
            st.subheader("Tambah MCU Baru")
            new_year = st.number_input("Tahun MCU", value=datetime.now().year, min_value=1945, max_value=3000, step=1)
            new_date = st.date_input("Tanggal MCU", min_value=datetime(1945, 1, 1), max_value=datetime(3000, 12, 31))
            new_file = st.file_uploader("Upload File MCU", type=["pdf", "png", "jpg", "jpeg"], key=f"new_file_{selected_nik}_{new_year}")
            new_diag = st.text_input("Diagnosis MCU Baru")
            new_rekom = st.text_area("Recommendation MCU Baru")
            
            if st.button("Save MCU Baru", key=f"btn_save_mcu_{selected_nik}_{new_year}"):
                saved_file_name = save_uploaded_file(new_file, selected_nik, new_year)
                if saved_file_name:
                    add_mcu_history(selected_nik, new_year, new_date.strftime("%Y-%m-%d"), calculate_mcu_expiry(new_date).strftime("%Y-%m-%d"), saved_file_name, new_diag, new_rekom)
                    st.success("MCU baru berhasil ditambahkan!")
                    safe_rerun()
                else:
                    st.error("File MCU belum diupload.")
            
            st.markdown("---")
            st.subheader("Edit/Delete Employee Data")
            edit_mode = st.checkbox("Edit employee data", key="edit_employee")
            if edit_mode:
                with st.form("edit_employee_form"):
                    employee_name_edit = st.text_input("Employee Name", employee_data['employee_name'])
                    birth_date_edit = st.date_input("Birth Date", pd.to_datetime(employee_data['birth_date']))
                    position_edit = st.text_input("Position", employee_data['position'])
                    email_edit = st.text_input("Employee Email", employee_data['email'])
                    hire_date_edit = st.date_input("Hire Date", pd.to_datetime(employee_data['hire_date']))
                    mcu_date_edit = st.date_input("Last MCU Date", pd.to_datetime(employee_data['mcu_date']))
                    work_period_edit = calculate_work_period(hire_date_edit)
                    mcu_expired_edit = calculate_mcu_expiry(mcu_date_edit).strftime("%Y-%m-%d")
                    examination_result_edit = st.text_area("Examination Result", employee_data['examination_result'])
                    diagnosis_edit = st.text_input("Diagnosis", employee_data['diagnosis'])
                    recommendation_edit = st.text_area("Recommendation", employee_data['recommendation'])
                    file_mcu_main_edit = employee_data['file_mcu_main']
                    submitted_edit = st.form_submit_button("Save Changes")
                    if submitted_edit:
                        # If user wants to upload new main MCU file
                        new_file_mcu_main = st.file_uploader("Upload New Main MCU File", type=['pdf', 'png', 'jpg', 'jpeg'], key="edit_main_mcu_file")
                        if new_file_mcu_main is not None:
                            file_mcu_main_edit = save_uploaded_file(new_file_mcu_main, selected_nik, pd.to_datetime(mcu_date_edit).year)
                        edit_employee(selected_nik, {
                            "employee_name": employee_name_edit,
                            "birth_date": birth_date_edit.strftime("%Y-%m-%d"),
                            "position": position_edit,
                            "hire_date": hire_date_edit.strftime("%Y-%m-%d"),
                            "work_period": work_period_edit,
                            "mcu_date": mcu_date_edit.strftime("%Y-%m-%d"),
                            "mcu_expired": mcu_expired_edit,
                            "file_mcu_main": file_mcu_main_edit,
                            "examination_result": examination_result_edit,
                            "diagnosis": diagnosis_edit,
                            "recommendation": recommendation_edit,
                            "status": check_mcu_status(mcu_expired_edit),
                            "email": email_edit
                        })
                        st.success("Data berhasil diupdate!")
                        safe_rerun()
            # DELETE employee: two-step confirmation using session_state
            if st.button("🗑️ Delete Employee", key="delete_emp_btn"):
                st.session_state["confirm_delete_emp"] = selected_nik
                st.warning("Klik tombol Konfirmasi Penghapusan untuk menghapus employee ini secara permanen.")
            if st.session_state.get("confirm_delete_emp") == selected_nik:
                if st.button("Konfirmasi Penghapusan (PERMANENT)", key="confirm_emp_delete_btn"):
                    ok = delete_employee(selected_nik)
                    if ok:
                        st.success("Employee data deleted permanently.")
                        # clear flag
                        st.session_state.pop("confirm_delete_emp", None)
                        safe_rerun()
                    else:
                        st.error("Gagal menghapus employee. Cek log.")
        else:
            st.warning("No data found for the search")
    else:
        st.warning("Database is empty. Please input MCU data first.")

elif page == "Export MCU Excel":
    show_logo()
    st.title("📤 Export MCU Data for Vendor")
    
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        df_emp = pd.read_sql("SELECT nik, employee_name, position FROM employee", conn)
        conn.close()
    except Exception as e:
        st.error("Failed to load employee data!")
        logging.error(f"Export DB error: {e}")
        df_emp = pd.DataFrame()
    
    # Tambahkan filter untuk memilih karyawan
    st.subheader("Filter Data untuk Export")
    
    col1, col2 = st.columns(2)
    with col1:
        positions = []
        if not df_emp.empty:
            positions = sorted(df_emp['position'].dropna().unique().tolist())
        selected_department = st.selectbox(
            "Pilih Department/Posisi",
            options=["All"] + positions
        )
    
    with col2:
        # Filter berdasarkan status MCU
        conn = sqlite3.connect("database/mcu_database.db")
        df_status = pd.read_sql("SELECT nik, status FROM employee", conn)
        conn.close()
        
        selected_status = st.selectbox(
            "Pilih Status MCU",
            options=["All", "Active", "Will Expire", "Expired", "No MCU"]
        )
    
    # Apply filters
    df_emp_filtered = df_emp.copy()
    if selected_department != "All":
        df_emp_filtered = df_emp_filtered[df_emp_filtered['position'] == selected_department]
    
    if selected_status != "All":
        df_emp_filtered = df_emp_filtered.merge(df_status, on='nik', how='left')
        df_emp_filtered = df_emp_filtered[df_emp_filtered['status'] == selected_status]
    
    st.info(f"Jumlah karyawan yang akan diexport: {len(df_emp_filtered)}")
    
    # Pilihan format export
    export_format = st.radio(
        "Format Export",
        ["Excel dengan Link GitHub", "Excel dengan Info Lengkap"]
    )
    
    export_btn = st.button("Export Data")
    
    if export_btn and not df_emp_filtered.empty:
        export_rows = []
        meta_years = []
        
        for idx, emp in df_emp_filtered.iterrows():
            nik = emp['nik']
            nama = emp['employee_name']
            position = emp.get('position', '')
            
            history_df = get_mcu_history_db(nik)
            last3 = history_df.head(3)
            
            if export_format == "Excel dengan Link GitHub":
                mcu_urls = []
                mcu_years = []
                for i, row in last3.iterrows():
                    github_url = get_github_mcu_url(nik, row['file_name'])
                    mcu_urls.append(github_url)
                    mcu_years.append(str(row['mcu_year']) if pd.notna(row['mcu_year']) else "")
                
                while len(mcu_urls) < 3:
                    mcu_urls.append("")
                    mcu_years.append("")
                
                export_rows.append({
                    "NIK": nik,
                    "Employee Name": nama,
                    "Position": position,
                    "MCU 1": mcu_urls[0],
                    "MCU 2": mcu_urls[1],
                    "MCU 3": mcu_urls[2]
                })
                meta_years.append(mcu_years)
            else:
                mcu_info = []
                for i, row in last3.iterrows():
                    mcu_info.append(
                        f"Tahun: {row['mcu_year']}, "
                        f"Tanggal: {row['mcu_date']}, "
                        f"Kedaluwarsa: {row['expired_date']}, "
                        f"Diagnosis: {row['diagnosis']}"
                    )
                while len(mcu_info) < 3:
                    mcu_info.append("")
                export_rows.append({
                    "NIK": nik,
                    "Employee Name": nama,
                    "Position": position,
                    "MCU Terbaru": mcu_info[0],
                    "MCU Ke-2": mcu_info[1],
                    "MCU Ke-3": mcu_info[2]
                })
        
        df_export = pd.DataFrame(export_rows)
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='MCU Data')
            
            workbook = writer.book
            worksheet = writer.sheets['MCU Data']
            
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            for i, col in enumerate(df_export.columns):
                try:
                    max_len = max(
                        df_export[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2
                except Exception:
                    max_len = len(col) + 2
                worksheet.set_column(i, i, max_len)
            
            if export_format == "Excel dengan Link GitHub":
                for row_idx, row_dict in enumerate(export_rows, start=1):
                    years = meta_years[row_idx - 1] if (row_idx - 1) < len(meta_years) else ["", "", ""]
                    for col_offset, col_name in enumerate(["MCU 1", "MCU 2", "MCU 3"]):
                        url = row_dict.get(col_name, "")
                        display_year = years[col_offset] if years[col_offset] else ""
                        if isinstance(url, str) and url.startswith("http"):
                            display_text = f"MCU {display_year}" if display_year else "MCU"
                            worksheet.write_url(row_idx, 3 + col_offset, url, string=display_text)
                        else:
                            pass
        
        excel_data = output.getvalue()
        st.download_button(
            label="⬇️ Download Excel File",
            data=excel_data,
            file_name="mcu_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif page == "Health Monitoring":
    show_logo()
    st.title("📈 Employee Health Monitoring")
    try:
        conn = sqlite3.connect("database/mcu_database.db")
        df = pd.read_sql("SELECT * FROM employee", conn)
        conn.close()
    except Exception as e:
        st.error("Failed to load data!")
        logging.error(f"Monitoring error: {e}")
        df = pd.DataFrame()
    if not df.empty and 'diagnosis' in df.columns:
        st.header("Health Trend Chart")
        st.subheader("Employee Age Histogram")
        df['birth_date'] = pd.to_datetime(df['birth_date'], errors='coerce')
        df['age'] = ((datetime.now() - df['birth_date']).dt.days // 365).fillna(0).astype(int)
        fig1, ax1 = plt.subplots(figsize=(4,3))
        ax1.hist(df['age'].dropna(), bins=10, color='skyblue', edgecolor='black')
        ax1.set_title("Employee Age Distribution")
        ax1.set_xlabel("Age (years)")
        ax1.set_ylabel("Count")
        st.pyplot(fig1)

        st.subheader("Diagnosis Trends per Year")
        df['mcu_date_parsed'] = pd.to_datetime(df['mcu_date'], errors='coerce')
        df['mcu_year'] = df['mcu_date_parsed'].dt.year
        if df['mcu_year'].isna().all():
            st.info("Tidak ada data MCU tahun untuk trend.")
        else:
            yearly_trend = df.groupby(['mcu_year', 'diagnosis']).size().unstack(fill_value=0)
            fig2, ax2 = plt.subplots(figsize=(5,3))
            yearly_trend.plot(kind='bar', stacked=True, ax=ax2)
            ax2.set_title('Health Diagnosis Trend per Year')
            ax2.set_xlabel('MCU Year')
            ax2.set_ylabel('Cases')
            ax2.legend(title='Diagnosis', bbox_to_anchor=(1,1))
            st.pyplot(fig2)

        st.subheader("MCU Trend per Month")
        df['mcu_month'] = df['mcu_date_parsed'].dt.to_period('M').astype(str)
        monthly_counts = df['mcu_month'].value_counts().sort_index()
        if monthly_counts.empty:
            st.info("Tidak ada data MCU per bulan.")
        else:
            fig3, (ax3, ax4) = plt.subplots(1, 2, figsize=(8,3))
            monthly_counts.plot(kind='line', marker='o', ax=ax3, color='green', linewidth=2)
            ax3.set_title('MCU Count per Month')
            ax3.set_ylabel('MCU Count')
            ax3.grid(True)
            ax3.tick_params(axis='x', rotation=45)
            monthly_counts.plot(kind='pie', ax=ax4, autopct='%1.1f%%',
                              startangle=90, shadow=True,
                              colors=plt.cm.Paired.colors)
            ax4.set_title('MCU Distribution per Month')
            ax4.set_ylabel('')
            st.pyplot(fig3)

        st.header("Health Risk Notification")
        common_issues = df['diagnosis'].value_counts().head(3)
        if not common_issues.empty:
            st.warning("**⚠️ Warning:** Some common health issues detected:")
            for issue, count in common_issues.items():
                st.write(f"- **{issue}**: {count} employee")
            expander = st.expander("📋 See Employee Details")
            for issue in common_issues.index:
                affected = df[df['diagnosis'] == issue]
                for idx, row in affected.iterrows():
                    expander.markdown(
                        f"<b>{row['employee_name']} ({row['nik']})</b> | Position: {row.get('position','-')}", unsafe_allow_html=True
                    )
        else:
            st.success("✅ No common health issues detected.")
    else:
        st.warning("Diagnosis data not available for monitoring.")
