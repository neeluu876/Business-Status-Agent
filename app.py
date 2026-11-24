import os

import pandas as pd
import streamlit as st

from agent import assess_company, prioritize_worklist

st.set_page_config(page_title="Business Status Verification Agent", page_icon="🔍", layout="wide")

st.title("🔍 Business Status Verification Agent")
st.caption(
    "A prototype that combines several signals to check whether a company flagged as "
    "'out of business' is actually still operating, then ranks which records to fix first. "
    "Most signals are simulated in this demo. Only the website check can be live."
)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.info(
        "Running in **rule-based mode** (no ANTHROPIC_API_KEY set). "
        "Set the variable to let Claude do the reasoning step.",
        icon="ℹ️",
    )

live_checks = st.sidebar.checkbox(
    "Use live website check", value=False,
    help="Makes a real HTTP request to each website you provide. All other signals stay simulated.",
)

tab1, tab2 = st.tabs(["🔎 Single Company Lookup", "📋 Batch Prioritization"])

with tab1:
    company = st.text_input("Company name", value="Acme Logistics LLC")
    website = st.text_input("Website (optional, used when live check is on)", value="")
    flagged = st.checkbox("Record is currently flagged out of business", value=True)
    if st.button("Run assessment", type="primary"):
        with st.spinner("Collecting signals and reasoning..."):
            result = assess_company(
                company, website=website or None, oob_flagged=flagged, live_checks=live_checks
            )

        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Status", result["status"])
            st.metric("Confidence (active)", f"{result['confidence']}/100")
            st.markdown(f"**Recommended action:** {result['recommended_action']}")
            st.caption(f"Mode: {result['mode']}")
        with col2:
            st.markdown("**Reasoning**")
            st.write(result["reasoning"])
            st.markdown("**Raw signals**")
            st.json(result["signals"])

with tab2:
    st.write(
        "Upload a CSV with a `company_name` column. Optional columns: `website`, "
        "`oob_flagged` (true/false, default true) and `impact` (a number, default 1)."
    )
    uploaded = st.file_uploader("Upload CSV", type="csv")

    if uploaded is not None:
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_csv("data/sample_companies.csv")
        st.caption("Using bundled sample dataset (data/sample_companies.csv)")

    if "company_name" not in df.columns:
        st.error("The CSV needs a `company_name` column.")
        st.stop()

    if st.button("Run batch assessment", type="primary"):
        with st.spinner(f"Assessing {len(df)} companies..."):
            results = []
            for _, row in df.iterrows():
                site = row.get("website")
                site = site if isinstance(site, str) and site.strip() else None
                flagged_value = row.get("oob_flagged", True)
                results.append(
                    assess_company(
                        row["company_name"],
                        website=site,
                        oob_flagged=str(flagged_value).strip().lower() not in ("false", "0", "no"),
                        impact=float(row.get("impact", 1.0)),
                        live_checks=live_checks,
                    )
                )
            ranked = prioritize_worklist(results)

        table = pd.DataFrame(
            [
                {
                    "Priority": r["priority_rank"],
                    "Company": r["company_name"],
                    "Flagged OOB": r["oob_flagged"],
                    "Status": r["status"],
                    "Confidence (active)": r["confidence"],
                    "Flag error likelihood": r["flag_error_likelihood"],
                    "Impact": r["impact"],
                    "Priority score": r["priority_score"],
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
