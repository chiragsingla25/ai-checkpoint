Summary of the previous chat:

## Summary: Q3 subscriber churn analysis for finance

**Goal:** Explain why subscriber churn rose in Q3. Finance wants an explanation by Friday.

**Repo and environment**
- Project: `~/work/retention-study`, branch `analysis/q3-lapses`, last commit `24453c5` ("Load payments and plans into duckdb").
- Stack: pandas, Jupyter, DuckDB for joins (database path in `ANALYTICS_DB_PATH`).
- Raw data: `data/raw/` holds the three vendor CSVs and a plans table saved from Snowflake. The user has finished with Snowflake and with `~/Downloads/vendor_export/`, so neither needs to be touched again.
- Notebook: `notebooks/01_churn_eda.ipynb` (renamed from `churn_eda.ipynb`). Use the new name.

**Data schema**
- `subscriptions`: customer_id, plan_id, start_date, churn_date, cancel_flag, is_test
- `payments`: customer_id, paid_at, amount_cents, status
- `plans`: plan_id, plan_name, monthly_price
- Joins: payments to subscriptions on customer_id; plans to subscriptions on plan_id.

**Decisions made**
- **Churn definition:** no successful payment for 45 days. The cancel_flag is not used, because many customers lapse without cancelling. A customer is churned on the first day the payment gap exceeds 45 days.
- **Population:** internal test accounts (`is_test`) are excluded. After exclusion, the count is **50,441 customers**. The earlier figure of 50,816 included test accounts and should not be used.
- **Headline churn rate:** **0.1259**, after rebuilding features. Show the definition alongside it on every chart.
- **Tenure:** `tenure_days = (churn_date.fillna(AS_OF) - start_date).dt.days`. Non-churned customers are censored at `AS_OF`. The `AS_OF` value is not recorded in the conversation, so confirm it in the code.
- **Model:** logistic regression with an L2 penalty, not gradient-boosted trees. Finance needs coefficients they can explain. Report odds ratios with confidence intervals. Standardise numeric columns on the training split only.
- **Features:** tenure, plan, price, signup month, and payment failures in the first 90 days.
- **Grain:** one row per customer for headline numbers. Count distinct customer_id, not rows.

**Pipeline state**
- Features were rebuilt with `python scripts/build_features.py --since 2024-07-01 --out data/features.parquet`.
- Still open from earlier: a convergence warning when fitting. It has not been resolved. Try scaling features, raising the iteration limit, or loosening the tolerance, then check whether coefficients stabilise. Also check for near-collinear features (correlation above about 0.8, or VIF).

**Deliverables**
- Methodology slide: data source and period, exclusions, term definitions, method in one sentence, main limitation. Put detail in an appendix.
- Finance summary: three slides. The assistant suggested drafting it in Google Drive, but the user has not confirmed that location.
- Charts: the user wants to use the dataviz skill. Log scales are acceptable only if clearly labelled.
- KPI naming: finance KPI definitions are at https://wiki.example.test/finance/retention-study/kpi-definitions. Nobody has read this page yet, so check naming against it.

**Open items and cautions**
- **Credential exposure:** the user pasted a Snowflake password into the chat. It should be treated as compromised and rotated. The user has not confirmed this has happened.
- **Unverified plan item:** the Google Drive draft was proposed by the assistant, not requested by the user.
- **Next step:** re-run the logistic regression on the rebuilt `data/features.parquet`, resolve or document the convergence warning, then draft the methodology and summary slides.
- **Reproducibility:** set seeds with `np.random.default_rng(seed)` and `random_state=seed`.
