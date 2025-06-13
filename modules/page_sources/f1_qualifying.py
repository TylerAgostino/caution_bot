from math import isnan
import streamlit as st
from modules import SubprocessManager
from modules.events import F1QualifyingEvent
from streamlit_autorefresh import st_autorefresh
from pandas import IndexSlice

def ui():
    st.title("F1 Qualifying")
    if 'elim_sessions' not in st.session_state:
        st.session_state.elim_sessions = [
            {
                'duration': '12',
                'advancing_cars': '15'
            }, {
                'duration': '10',
                'advancing_cars': '10'
            }
        ]
    if 'final_session' not in st.session_state:
        st.session_state.final_session = {
            'duration': '8',
            'advancing_cars': '0'
        }

    with st.container():
        col1, col2, col3, col4 = st.columns((1,1,1,4))
        col2.subheader("Duration (Mins)")
        col3.subheader("Advancing Cars")
        n=1
        for i, session in enumerate(st.session_state.elim_sessions):
            col1, col2, col3, col4 = st.columns((1,1,1,4))
            col1.subheader(f'Q{n}')
            st.session_state.elim_sessions[i]['duration'] = col2.text_input("Duration (Mins)", label_visibility='hidden', key=f"{i}_duration", value=session['duration'])
            st.session_state.elim_sessions[i]['advancing_cars'] = col3.text_input("Advancing Cars", label_visibility='hidden', key=f"{i}_advancing_cars", value=session['advancing_cars'])
            if col4.button("Remove", key=f"remove_{i}"):
                st.session_state.elim_sessions.remove(session)
                st.rerun()
            st.write('---')
            n += 1

        col1, col2, col3, col4 = st.columns((1,1,1,4))
        col1.subheader(f'Q{n}')
        st.session_state.final_session = {
            'duration': col2.text_input("Duration (Mins)", key=f"final_duration", label_visibility='hidden', value=st.session_state.final_session['duration']),
            'advancing_cars': col3.text_input("Advancing Cars", key=f"final_advancing_cars", label_visibility='hidden', disabled=True, value='0')
        }
        if col4.button("Add Session"):
            st.session_state.elim_sessions.append({
                'duration': '',
                'advancing_cars': ''
            })
            st.rerun()


    all_sessions = [*st.session_state.elim_sessions, st.session_state.final_session]
    session_lengths = ", ".join([s['duration'] for s in all_sessions]) #st.text_input("Session Lengths (comma-separated)", "1, 1, 1")
    advancing_cars = ", ".join([s['advancing_cars'] for s in all_sessions])  # st.text_input("Advancing Cars (comma-separated)", "8, 5, 0")
    wait_between_sessions = col1.number_input("Wait Between Sessions (seconds)", value=120)

    if st.button("Stop"):
        if 'f1_subprocess_manager' in st.session_state:
            st.session_state.f1_subprocess_manager.stop()
        st.session_state.refresh = False

    if st.button("Start"):
        st.session_state.event = F1QualifyingEvent(session_lengths, advancing_cars, wait_between_sessions=wait_between_sessions)
        st.session_state.f1_subprocess_manager = SubprocessManager([st.session_state.event.run])
        st.session_state.f1_subprocess_manager.start()
        st.session_state.refresh = True

    if 'event' in st.session_state:
        c1, c2, _ = st.columns([1, 1, 2])
        c1.header(st.session_state.event.subsession_time_remaining)
        c2.header(st.session_state.event.subsession_name)
        leaderboard = st.session_state.event.leaderboard_df.copy()
        # convert index to column
        leaderboard['#'] = leaderboard.index
        leaderboard = leaderboard[['#'] + [col for col in leaderboard.columns if col != '#']]
        leaderboard.reset_index(inplace=True, drop=True)
        leaderboard.index += 1

        subsession_index = int(st.session_state.event.subsession_name.split('Q')[1])-1
        driver_at_risk = [int(i) for i in advancing_cars.split(',')][subsession_index]
        driver_at_risk = [driver_at_risk-1] if 0<int(driver_at_risk)<=len(leaderboard) else []

        st.dataframe(
            leaderboard.style
                .highlight_between(subset=leaderboard.columns[2:], color='yellow', axis=1, left=0, right=10000)
                .map(lambda _: 'background-color: orange; color:black', subset=(leaderboard.index[driver_at_risk],))
                .highlight_min(subset=leaderboard.columns[2:], color='green', axis=1)
                .highlight_min(subset=leaderboard.columns[2:], color='purple', axis=0)
                .format(subset=leaderboard.columns[2:], formatter=lambda x: f"{int(x // 60):02}:{int(x % 60):02}.{int((x % 1) * 1000):03}" if isinstance(x, (int, float)) and not isnan(x) else x)
                .map(lambda x: 'background-color: grey; color:black' if st.session_state.event.waiting_on and x in st.session_state.event.waiting_on else '')
            ,width=600, height=1000, use_container_width=False)

    if st.session_state.get('refresh', False):
        st_autorefresh()
    else:
        st_autorefresh(limit=1)

f1_qualifying = st.Page(ui, title='F1 Qualifying', url_path='f1_qualifying')