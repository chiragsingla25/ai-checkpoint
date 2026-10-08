Summary of the previous chat:

**Summary for continuing the subscriber churn analysis (Q3 lapses)**

**Goal:** Explain why subscriber churn rose in Q3, for finance, due Friday.

**Project setup**
- Repo: `~/work/subscriber-health`, branch `analysis/q3-lapses`, last commit `39f040d` ("Load payments and plans into duckdb").
- Source data: three vendor CSVs now copied to `data/raw/` (subscriptions, payments, plans). Ignore `~/Downloads/vendor_export/` from here on. The plans table was also pulled via Snowflake and saved locally, so no further Snowflake access is needed.
- Stack: pandas, Jupyter, and duckdb for joins (database path in `ANALYTICS_DB_PATH`).
- EDA notebook: `notebooks/01_churn_eda.ipynb` (renamed from `churn_eda.ipynb`).

**Table columns**
- subscriptions: customer_id, plan_id, start_date, churn_date, cancel_flag, is_test
- payments: customer_id, paid_at, amount_cents, status
- plans: plan_id, plan_name, monthly_price

**Agreed decisions**
- **Churn definition:** no successful payment for 60 days. The customer is churned on the first day the payment gap exceeds 60 days. `cancel_flag` is deliberately not used.
- **Population:** exclude `is_test` accounts. After deduplication and exclusion, there are **46,088 customers** (an earlier figure of 46,910 included test accounts and was wrong).
- **Headline churn rate:** **0.2373** on the 46,088 population. Show the churn definition alongside this number on every chart.
- **Dates:** the date column has three formats. Parse each with an explicit `format=` and `errors='coerce'`, then inspect the NaT rows. Do not rely on inference, because day/month order is ambiguous.
- **Tenure:** `(churn_date.fillna(AS_OF) - start_date).dt.days`, with non-churned customers censored at `AS_OF`. (`AS_OF` is not yet defined in the notebook.)
- **Model:** logistic regression with L2 penalty, standardised numeric features on the training split, reported as odds ratios with confidence intervals. No gradient-boosted trees, since finance needs readable coefficients.
- **Features:** tenure, plan, price, signup month, and payment failures in the first 90 days.

**Pipeline**
- Rebuild features with: `python scripts/build_features.py --since 2025-02-01 --out data/features.parquet`
- Use the dataviz skill for charts.
- Naming should follow the finance KPI definitions at https://wiki.example.test/finance/subscriber-health/kpi-definitions. This page has not been read yet in this conversation.

**Open items and cautions**
- **Security:** a Snowflake password (`SNOWFLAKE_PASSWORD`, an `sk-` style token) was pasted into the chat. Treat it as exposed and rotate it if it is real. Do not paste credentials into chats again.
- **Next step:** re-run the logistic regression on the rebuilt features.
- **Proposed, not yet agreed:** a three-slide finance summary in Google Drive. The user has not confirmed this format or location.
- The notebook has not yet been checked against the new 46,088 population or the rebuilt features.
