Summary of the previous chat:

## Summary: Q3 subscriber churn analysis for finance

**Goal:** Explain why subscriber churn rose in Q3, for finance, due Friday. The deck needs a methodology slide.

**Repo and files**
- Project: `~/work/lapse-model`, branch `analysis/q3-churn`, last commit `182ed4a` ("Load payments and plans into duckdb").
- Vendor CSVs are in `data/raw/`. The user has copied them there and says to ignore `~/Downloads/vendor_export/` from now on.
- Plans table was pulled from Snowflake and saved to `data/raw/`. No further Snowflake access is needed.
- Main notebook: `notebooks/01_churn_eda.ipynb` (renamed from `churn_eda.ipynb`).
- Feature build: `python scripts/build_features.py --since 2025-01-01 --out data/features.parquet`.
- Tools: pandas, Jupyter, DuckDB for joins, scikit-learn.

**Data**
- `subscriptions`: customer_id, plan_id, start_date, churn_date, cancel_flag, is_test
- `payments`: customer_id, paid_at, amount_cents, status
- `plans`: plan_id, plan_name, monthly_price
- Joins: payments to subscriptions on customer_id; plans on plan_id.
- Exclude `is_test` accounts (internal test accounts).
- Date column has three formats. Parse each with an explicit `format=` and `errors='coerce'`, then inspect the NaT rows.
- Customer counts: an earlier figure of 51,896 (after dropping duplicates) included test accounts. The correct population after excluding `is_test` is **51,225**.

**Churn definition (agreed)**
- A customer is churned on the first day their payment gap exceeds **75 days** with no successful payment.
- `cancel_flag` is not used, because many customers stop paying without cancelling.
- Tenure: `df["tenure_days"] = (df["churn_date"].fillna(AS_OF) - df["start_date"]).dt.days`. Non-churned customers are censored at `AS_OF`. `AS_OF` is not yet defined in the notebook and needs to be set.
- After the feature rebuild, the overall churn rate is **0.0983**. Show it on every chart with the definition next to it.

**Method (agreed)**
- Model: **logistic regression with L2 penalty**. Gradient-boosted trees were ruled out because finance needs readable coefficients.
- Feature table: tenure, plan, price, signup month, payment failures in the first 90 days.
- Standardise numeric features, fitting the scaler on the training split only.
- Handle missing numerics with median plus an `is_missing` indicator. Investigate missing plan values before filling them with an explicit "unknown" category.
- Report odds ratios with confidence intervals.
- Use `random_state` / `default_rng(seed)` for reproducibility, and do not tune the seed.
- Evaluate with cross-validation or repeated splits, split by time where order matters, and report the spread of AUC.
- A convergence warning appeared in an earlier fit. It is not confirmed as resolved. Check for near-collinear features (correlation above about 0.8, or VIF) and near-constant columns.

**Methodology slide contents (planned)**
Data source and period, main exclusions (test accounts, duplicates), key definitions (churn, tenure, censoring), method in one sentence, main limitation. Detail goes in an appendix. Also include a data-cleaning audit table (step, rows before, rows after, reason), generated from the notebook.

**Other decisions and guidance**
- Recent joiners: restrict to a minimum observation window or use a censoring-aware method.
- Outlier payment amounts: investigate first; winsorise only if documented, keeping raw values in the audit table.
- Charts: use the dataviz skill. Cohort charts are line charts by months since start. Use seaborn for drafting and matplotlib for polish. Show medians in headlines with distributions in the appendix.
- Naming: `is_`/`has_` prefix for booleans, units in names (e.g., `tenure_days`).
- Notebook hygiene before sharing: restart and run all, remove dead cells, put paths and parameters in one top cell, clear outputs with customer-level data.
- Save intermediates as parquet, not CSV.

**Security issue to flag**
The user pasted a Snowflake password (`SNOWFLAKE_PASSWORD=...`) into the chat. The assistant advised rotating it if it is real. It should be treated as exposed. Do not repeat it in any output.

**Next steps**
1. Set `AS_OF` and confirm the 51,225 population and the 0.0983 churn rate after the rebuild.
2. Re-run the logistic regression on the rebuilt `data/features.parquet`, checking for the convergence warning and collinearity.
3. Produce odds ratios with confidence intervals and cross-validated AUC.
4. Draft the methodology slide and the three-slide finance summary. The Google Drive location for the summary was mentioned only in the assistant's wrap-up and has not been confirmed by the user.
5. Check the KPI naming against the finance wiki (`https://wiki.example.test/finance/lapse-model/kpi-definitions`). Its contents have not been reviewed in this conversation.
