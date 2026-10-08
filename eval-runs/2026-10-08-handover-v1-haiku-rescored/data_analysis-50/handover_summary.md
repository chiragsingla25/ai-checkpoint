Summary of the previous chat:

**Project:** Q3 subscriber churn analysis for finance, due Friday. Repo `~/work/retention-study`, branch `analysis/q3-lapses`, last commit `24453c5` ("Load payments and plans into duckdb"). Stack: pandas, Jupyter, DuckDB for joins.

**Data**
- Three vendor CSVs, originally in `~/Downloads/vendor_export/`. The user has copied them to `data/raw/` and will not use the Downloads folder again. Don't open files in Excel.
- `subscriptions`: customer_id, plan_id, start_date, churn_date, cancel_flag, is_test
- `payments`: customer_id, paid_at, amount_cents, status
- `plans`: plan_id, plan_name, monthly_price. Pulled via the Snowflake connector and saved to `data/raw/`. No further Snowflake access is needed.
- Joins: payments to subscriptions on customer_id; plans to subscriptions on plan_id.
- The user pasted a Snowflake password into the chat. Treat it as exposed. It should be rotated if real, and it should not be reused or repeated.

**Definitions and decisions**
- **Churn:** no successful payment for 45 days. The `cancel_flag` column is deliberately not used, because many customers stop paying without cancelling. A customer is churned on the first day their payment gap exceeds 45 days.
- **Population:** internal test accounts (`is_test`) are excluded. The count was 50,816 after deduplication, but that included test accounts. The correct figure is **50,441**.
- **Overall churn rate after rebuild:** **0.1259**. Show it on every chart with the definition beside it.
- **Tenure:** `tenure_days = (churn_date.fillna(AS_OF) - start_date).dt.days`. Non-churned customers are censored at AS_OF.
- **Grain:** one row per customer for headline numbers. Count distinct customer_id, not rows, to avoid double counting plan changes.
- **Model:** logistic regression with L2 penalty, standardised numeric features fitted on the training split, reported as odds ratios with confidence intervals. Gradient-boosted trees were ruled out because finance needs readable coefficients.
- **Planned features:** tenure, plan, price, signup month, payment failures in the first 90 days.
- **Notebooks:** `notebooks/churn_eda.ipynb` was renamed to `notebooks/01_churn_eda.ipynb`.
- **Feature build:** `python scripts/build_features.py --since 2024-07-01 --out data/features.parquet`.
- **Reference material:** finance KPI definitions are on the wiki at https://wiki.example.test/finance/retention-study/kpi-definitions. The user wants the dataviz skill used for charts. Neither has been opened or checked in this conversation.

**Open issues**
- A convergence warning appeared when fitting the logistic regression. It has not been resolved. The suggested fixes are scaling features, raising the iteration limit, or loosening tolerance, then checking whether coefficients move. If they keep moving, suspect near-collinear features. Check with a correlation matrix (pairs above about 0.8) or VIFs.
- Check `is_test` leakage and duplicate rows across train and test, since the model is not yet validated.
- The deck needs a methodology slide: source and period, exclusions, term definitions, method in one sentence, and main limitation. Put detail in an appendix.

**Next steps**
1. Re-run the logistic regression on the rebuilt features (population 50,441, churn rate 0.1259).
2. Resolve the convergence warning and check coefficient stability.
3. Build the methodology and finance summary slides. The user has not yet confirmed where these will live. The earlier mention of Google Drive came from the assistant, not the user, so confirm it before relying on it.
