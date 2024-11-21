import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import pandas as pd

# Supabase configuration
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Helper functions
def get_current_period():
    today = datetime.today()
    day = today.day
    period = 'Part 1' if day <= 15 else 'Part 2'
    start_day = 1 if period == 'Part 1' else 16
    end_day = 15 if period == 'Part 1' else (today.replace(month=today.month+1, day=1) - timedelta(days=1)).day
    start_date = today.replace(day=start_day)
    end_date = today.replace(day=end_day)
    return period, start_date, end_date

def authenticate_user(email, phone_number):
    response = supabase.table('users').select('*').eq('email', email).eq('phone_number', phone_number).execute()
    if response.data:
        return response.data[0]  # Return user record
    else:
        return None

def get_user_entries(user_id, start_date, end_date):
    response = supabase.table('work_done').select('*').eq('user_id', user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
    return pd.DataFrame(response.data)

def save_entries(entries):
    for entry in entries:
        # Check if entry exists
        response = supabase.table('work_done').select('*').eq('user_id', entry['user_id']).eq('date', entry['date']).execute()
        if response.data:
            # Update existing entry
            supabase.table('work_done').update(entry).eq('user_id', entry['user_id']).eq('date', entry['date']).execute()
        else:
            # Insert new entry
            supabase.table('work_done').insert(entry).execute()

def get_admin_report(start_date, end_date):
    response = supabase.table('work_done').select('*').gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return None
    users_response = supabase.table('users').select('*').execute()
    users_df = pd.DataFrame(users_response.data)
    df = df.merge(users_df, left_on='user_id', right_on='id', suffixes=('_work', '_user'))
    return df

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
        email = st.text_input("Email")
        phone_number = st.text_input("Phone Number")
        submitted = st.form_submit_button("Login")
        if submitted:
            user = authenticate_user(email, phone_number)
            if user:
                st.session_state['authenticated'] = True
                st.session_state['user'] = user
                st.success("Logged in successfully!")
            else:
                st.error("Invalid credentials. Please try again.")
else:
    user = st.session_state['user']
    st.sidebar.write(f"Logged in as: {user['email']}")
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

        report_df = get_admin_report(start_date, end_date)
        if report_df is not None:
            # Aggregate data
            summary_df = report_df.groupby(['user_id', 'email', 'last_name']).agg({'hours_worked': 'sum'}).reset_index()
            st.subheader("Summary")
            st.table(summary_df)

            csv = report_df.to_csv(index=False)
            st.download_button("Download Detailed Report CSV", csv, "report.csv", "text/csv")
        else:
            st.info("No data available for the last completed period.")
    else:
        st.header("Work Entry")

        period, start_date, end_date = get_current_period()
        st.write(f"Current Period: **{period}** ({start_date.date()} to {end_date.date()})")

        # Fetch existing entries
        entries_df = get_user_entries(user['id'], start_date, end_date)

        # Prepare dates
        date_range = pd.date_range(start=start_date, end=end_date)
        if entries_df.empty:
            # Create empty dataframe
            entries_df = pd.DataFrame({
                'date': date_range,
                'hours_worked': [0]*len(date_range),
                'tasks_done': ['']*len(date_range),
                'facility': ['']*len(date_range),
            })
        else:
            entries_df['date'] = pd.to_datetime(entries_df['date'])
            entries_df = entries_df.set_index('date').reindex(date_range).reset_index()

        with st.form("entry_form"):
            st.write("Fill in your work details for each day.")
            entries = []
            for idx, row in entries_df.iterrows():
                date = row['index'].date()
                st.subheader(f"Date: {date}")
                hours_worked = st.number_input(f"Hours Worked on {date}", min_value=0, max_value=24, value=int(row.get('hours_worked', 0)), key=f"hours_{idx}")
                tasks_done = st.text_input(f"Tasks Done on {date}", value=row.get('tasks_done', ''), key=f"tasks_{idx}")
                facility = st.text_input(f"Facility on {date}", value=row.get('facility', ''), key=f"facility_{idx}")

                entry = {
                    'user_id': user['id'],
                    'date': row['index'].isoformat(),
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
                save_entries(entries)
                st.success("Entries saved successfully!")

