import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import pandas as pd

# Database configuration
DB_CONFIG = {
    "host": "aws-0-us-east-1.pooler.supabase.com",
    "port": "6543",
    "database": "postgres",
    "user": "postgres.vrteqedymxdwhcztvmur",
    "password": "7pwF28rp6acy80yV"
}

# Helper function to get database connection
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

# Helper functions
def get_current_period():
    today = datetime.today()
    day = today.day
    period = 'Part 1' if day <= 15 else 'Part 2'
    start_day = 1 if period == 'Part 1' else 16
    end_day = 15 if period == 'Part 1' else (today.replace(month=today.month + 1, day=1) - timedelta(days=1)).day
    start_date = today.replace(day=start_day)
    end_date = today.replace(day=end_day)
    return period, start_date, end_date

def authenticate_user(last_name, phone_number):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE last_name = %s AND phone_number = %s",
                (last_name, phone_number)
            )
            result = cur.fetchone()
            return dict(result) if result else None

def get_user_entries(user_id, start_date, end_date):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM work_done 
                WHERE user_id = %s 
                AND date >= %s 
                AND date <= %s
                ORDER BY date
                """,
                (user_id, start_date.isoformat(), end_date.isoformat())
            )
            results = cur.fetchall()
            if results:
                df = pd.DataFrame([dict(row) for row in results])
                df['date'] = pd.to_datetime(df['date'])
                df['hours_worked'] = df['hours_worked'].astype(float)
                return df
            return pd.DataFrame()

def save_entries(entries):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for entry in entries:
                # Check if entry exists
                cur.execute(
                    "SELECT id FROM work_done WHERE user_id = %s AND date = %s",
                    (entry['user_id'], entry['date'])
                )
                existing = cur.fetchone()
                
                if existing:
                    # Update existing entry
                    cur.execute(
                        """
                        UPDATE work_done 
                        SET hours_worked = %s, tasks_done = %s, facility = %s,
                            period = %s, month = %s, year = %s
                        WHERE user_id = %s AND date = %s
                        """,
                        (
                            entry['hours_worked'], entry['tasks_done'], entry['facility'],
                            entry['period'], entry['month'], entry['year'],
                            entry['user_id'], entry['date']
                        )
                    )
                else:
                    # Insert new entry
                    cur.execute(
                        """
                        INSERT INTO work_done 
                        (user_id, date, hours_worked, tasks_done, facility, period, month, year)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            entry['user_id'], entry['date'], entry['hours_worked'],
                            entry['tasks_done'], entry['facility'], entry['period'],
                            entry['month'], entry['year']
                        )
                    )
            conn.commit()

def get_admin_report(start_date, end_date):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.*, u.last_name, u.phone_number 
                FROM work_done w
                JOIN users u ON w.user_id = u.id
                WHERE w.date >= %s AND w.date <= %s
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            results = cur.fetchall()
            if not results:
                return None
            return pd.DataFrame([dict(row) for row in results])

# Streamlit app
st.title("Doctor Scheduling and Billing App")

# Session state for authentication
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'user' not in st.session_state:
    st.session_state['user'] = None

# Authentication
if not st.session_state['authenticated']:
    st.header("Login")
    with st.form("login_form"):
        last_name = st.text_input("Last Name")
        phone_number = st.text_input("Phone Number")
        submitted = st.form_submit_button("Login")
        if submitted:
            try:
                user = authenticate_user(last_name, phone_number)
                if user:
                    st.session_state['authenticated'] = True
                    st.session_state['user'] = user
                    st.success("Logged in successfully!")
                else:
                    st.error("Invalid credentials. Please try again.")
            except Exception as e:
                st.error(f"Login failed: {str(e)}")
else:
    user = st.session_state['user']
    st.sidebar.write(f"Logged in as: {user['last_name']}")
    logout = st.sidebar.button("Logout")
    if logout:
        st.session_state['authenticated'] = False
        st.session_state['user'] = None
        st.experimental_rerun()

    # Check if user is admin
    if user.get('is_admin', False):
        st.header("Admin Dashboard")
        st.write("Download aggregated reports for the last 15-day period.")

        period, start_date, end_date = get_current_period()
        # Adjust dates for the last completed period
        if period == 'Part 1':
            end_date = start_date - timedelta(days=1)
            start_date = end_date.replace(day=16)
        else:
            end_date = start_date - timedelta(days=1)
            start_date = end_date.replace(day=1)

        try:
            report_df = get_admin_report(start_date, end_date)
            if report_df is not None:
                # Aggregate data
                summary_df = report_df.groupby(['user_id', 'phone_number', 'last_name']).agg({'hours_worked': 'sum'}).reset_index()
                st.subheader("Summary")
                st.table(summary_df)

                csv = report_df.to_csv(index=False)
                st.download_button("Download Detailed Report CSV", csv, "report.csv", "text/csv")
            else:
                st.info("No data available for the last completed period.")
        except Exception as e:
            st.error(f"Error generating report: {str(e)}")
    else:
        st.header("Work Entry")

        period, start_date, end_date = get_current_period()
        st.write(f"Current Period: **{period}** ({start_date.date()} to {end_date.date()})")

        try:
            # Fetch existing entries
            entries_df = get_user_entries(user['id'], start_date, end_date)
            
            # Prepare dates
            date_range = pd.date_range(start=start_date, end=end_date)
            
            if entries_df.empty:
                # Create empty dataframe with all dates
                entries_df = pd.DataFrame({
                    'date': date_range,
                    'hours_worked': [0.0] * len(date_range),
                    'tasks_done': [''] * len(date_range),
                    'facility': [''] * len(date_range),
                })
            else:
                # Create a template DataFrame with all dates
                template_df = pd.DataFrame({'date': date_range})
                
                # Merge existing entries with template to ensure all dates are present
                entries_df = pd.merge(
                    template_df,
                    entries_df,
                    on='date',
                    how='left'
                )
                
                # Fill missing values
                entries_df['hours_worked'] = entries_df['hours_worked'].fillna(0.0)
                entries_df['tasks_done'] = entries_df['tasks_done'].fillna('')
                entries_df['facility'] = entries_df['facility'].fillna('')

            with st.form("entry_form"):
                st.write("Fill in your work details for each day.")
                entries = []
                
                # Sort DataFrame by date to ensure consistent display
                entries_df = entries_df.sort_values('date')
                
                for idx, row in entries_df.iterrows():
                    date = row['date'].date()
                    st.subheader(f"Date: {date}")
                    
                    # Convert hours_worked to float before converting to int for the input
                    current_hours = float(row['hours_worked']) if pd.notnull(row['hours_worked']) else 0.0
                    
                    hours_worked = st.number_input(
                        f"Hours Worked on {date}",
                        min_value=0.0,
                        max_value=24.0,
                        value=float(current_hours),
                        key=f"hours_{date}"  # Changed key to use date instead of idx
                    )
                    
                    current_tasks = str(row['tasks_done']) if pd.notnull(row['tasks_done']) else ''
                    tasks_done = st.text_input(
                        f"Tasks Done on {date}",
                        value=current_tasks,
                        key=f"tasks_{date}"  # Changed key to use date instead of idx
                    )
                    
                    current_facility = str(row['facility']) if pd.notnull(row['facility']) else ''
                    facility = st.text_input(
                        f"Facility on {date}",
                        value=current_facility,
                        key=f"facility_{date}"  # Changed key to use date instead of idx
                    )

                    entry = {
                        'user_id': user['id'],
                        'date': row['date'].isoformat(),
                        'period': period,
                        'month': start_date.month,
                        'year': start_date.year,
                        'hours_worked': hours_worked,
                        'tasks_done': tasks_done,
                        'facility': facility
                    }
                    entries.append(entry)

                submitted = st.form_submit_button("Save Entries")
                if submitted:
                    try:
                        save_entries(entries)
                        st.success("Entries saved successfully!")
                    except Exception as e:
                        st.error(f"Error saving entries: {str(e)}")
        except Exception as e:
            st.error(f"Error loading entries: {str(e)}")
