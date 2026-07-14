import os
import pandas as pd
import streamlit as st

from agent import assess_company, prioritize_worklist

st.set_page_config(page_title="Business Status Verification Agent", page_icon="🔍", layout="wide")

st.title("🔍 Business Status Verification Agent")
st.caption(
    "An agentic pipeline that cross-references multiple weak signals to verify whether "
    "a company flagged as 'out of business' is actually correct — and prioritizes which "
    "records to fix first."
)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.info(
        "Running in **rule-based demo mode** (no ANTHROPIC_API_KEY set). "
        "Set the env var to let Claude perform the reasoning step instead.",
        icon="ℹ️",
    )

tab1, tab2 = st.tabs(["🔎 Single Company Lookup", "📋 Batch Prioritization"])

with tab1:
    company = st.text_input("Company name", value="Acme Logistics LLC")
    if st.button("Run assessment", type="primary"):
        with st.spinner("Collecting signals and reasoning..."):
            result = assess_company(company)

        status = result["status"]
        color = {
            "Active": "green",
            "Likely Active": "green",
            "Uncertain": "orange",
            "Likely Defunct": "red",
            "Defunct": "red",
        }.get(status, "gray")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Status", status)
            st.metric("Confidence (active)", f"{result['confidence']}/100")
            st.markdown(f"**Recommended action:** {result['recommended_action']}")
            st.caption(f"Mode: {result['mode']}")
        with col2:
            st.markdown("**Reasoning**")
            st.write(result["reasoning"])
            st.markdown("**Raw signals**")
            st.json(result["signals"])

with tab2:
    st.write("Upload a CSV with a `company_name` column, or use the bundled sample dataset.")
    uploaded = st.file_uploader("Upload CSV", type="csv")

    if uploaded is not None:
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_csv("data/sample_companies.csv")
        st.caption("Using bundled sample dataset (data/sample_companies.csv)")

    if st.button("Run batch assessment", type="primary"):
        with st.spinner(f"Assessing {len(df)} companies..."):
            results = [assess_company(name) for name in df["company_name"]]
            ranked = prioritize_worklist(results)

        table = pd.DataFrame(
            [
                {
                    "Priority": r["priority_rank"],
                    "Company": r["company_name"],
                    "Status": r["status"],
                    "Confidence": r["confidence"],
                    "Recommended Action": r["recommended_action"],
                }
                for r in ranked
            ]
        )
        st.dataframe(table, use_container_width=True, hide_index=True)

        st.download_button(
            "Download prioritized worklist (CSV)",
            table.to_csv(index=False),
            file_name="prioritized_worklist.csv",
            mime="text/csv",
        )
