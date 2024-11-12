import streamlit as st


def ui():
    if 'vsc' not in st.session_state:
        st.session_state.vsc = False

    st.checkbox('Activate VSC', key='vsc')
    st.write('VSC Active:', st.session_state.vsc)


random_vsc_bot = st.Page(ui, title='Random VSC Bot', url_path='random_vsc_bot')
