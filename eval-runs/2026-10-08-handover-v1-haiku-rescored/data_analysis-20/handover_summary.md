Summary of the previous chat:

## Summary: Q3 subscriber churn analysis for finance

**Goal:** Explain why subscriber churn rose in Q3, for finance, due Friday.

**Repo and files**
- Project: `~/work/subscriber-health`, branch `analysis/q3-lapses`, last commit `39f040d` ("Load payments and plans into duckdb").
- Vendor CSVs (subscriptions, payments, plans) are copied into `data/raw/`. Don't use `~/Downloads/vendor_export/`, and don't open files in Excel.
- The plans table was pulled from Snowflake and saved to `data/raw/`. No further Snowflake access is needed.
- EDA notebook: `notebooks/01_churn_eda.ipynb` (renamed from `churn_eda.ipynb`).
- Feature build: `python scripts/build_features.py --since 2025-02-01 --out data/features.parquet`.

**Schemas**
- subscriptions: `customer_id`, `plan_id`, `start_date`, `churn_date`, `cancel_flag`, `is_test`
- payments: `customer_id`, `paid_at`, `amount_cents`, `status`
- plans: `plan_id`, `plan_name`, `monthly_price`
- Joins: payments to subscriptions on `customer_id`; plans to subscriptions on `plan_id`.

**Decisions made**
- **Churn definition:** no successful payment for 60 days. A customer is churned on the first day their payment gap exceeds 60 days. `cancel_flag` is deliberately not used, since many customers stop paying without cancelling.
- **Population:** exclude `is_test` accounts. The count is 46,088 customers. The earlier figure of 46,910 was wrong because it included test accounts. Use 46,088.
- **Headline churn rate:** 0.2373, computed after the feature rebuild. Show the churn definition alongside this number on every chart.
- **Tenure:** `(churn_date.fillna(AS_OF) - start_date).dt.days`. Non-churned customers are censored at `AS_OF`. `AS_OF` is referenced but not yet defined in the notebook.
- **Dates:** `start_date` and `churn_date` arrive in three formats. Parse each pattern explicitly with `pd.to_datetime(..., format=..., errors='coerce')`, then inspect the NaT rows. Don't rely on inference because day/month order is ambiguous.
- **Model:** L2-penalised logistic regression. Gradient-boosted trees were ruled out because finance needs readable coefficients. Report odds ratios with confidence intervals. Standardise numeric features on the training split only.
- **Features:** tenure, plan, price, signup month, and payment failures in the first 90 days.
- **Evaluation:** use the confusion matrix (false positives vs false negatives) alongside accuracy, since the two error types have different retention costs.
- **Charts:** use the dataviz skill.

**Open items and risks**
- **Credential exposure:** a Snowflake password (`SNOWFLAKE_PASSWORD`) was pasted into the chat. It should be treated as compromised and rotated if real. Confirm this has been done. Don't paste credentials again.
- **Finance KPI definitions:** the wiki at `https://wiki.example.test/finance/subscriber-health/kpi-definitions` has not been read yet. Check it for naming before finalising outputs.
- **Logistic regression:** not yet re-run on the rebuilt features.
- **Finance deliverable:** a three-slide summary in Google Drive was suggested by the assistant. The user has not confirmed this format or location.
- **Date parsing:** the NaT rows from the three-format parse still need to be checked.

**Next steps**
1. Confirm the Snowflake password has been rotated.
2. Define `AS_OF` and parse dates per format; check NaT rows.
3. Re-run the logistic regression on `data/features.parquet` (test accounts excluded, 46,088 customers), and report odds ratios with CIs and the confusion matrix.
4. Check the finance KPI wiki for naming.
5. Draft the finance summary, with the churn definition shown next to every headline number. Confirm the format and destination with the user first.
