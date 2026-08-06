import os
import sys
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge

from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"

def get_db_connection():
    import sqlalchemy as sa
    db_url = os.getenv("DATABASE_URL")
    fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
    try:
        engine = sa.create_engine(db_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return engine, "postgres"
    except Exception:
        engine = sa.create_engine(f"sqlite:///{fallback_db}")
        return engine, "sqlite"

def check_retail_event(dt):
    m, d = dt.month, dt.day
    if (m == 7 and d == 4) or (m == 12 and d in [24, 25, 31]) or (m == 1 and d == 1) or (m == 11 and 23 <= d <= 29):
        return 1.0
    return 0.0

def train_and_forecast_slice(sales_slice_df, slice_channel, slice_category, engine):
    if sales_slice_df.empty or len(sales_slice_df) < 14:
        return []

    daily_sales = sales_slice_df.groupby('date_day')['net_sales'].sum().reset_index()
    daily_sales = daily_sales.sort_values('date_day').reset_index(drop=True)
    daily_sales['net_sales'] = daily_sales['net_sales'].astype(float)

    idx = pd.date_range(daily_sales['date_day'].min(), daily_sales['date_day'].max())
    daily_sales = daily_sales.set_index(pd.DatetimeIndex(daily_sales['date_day']))
    daily_sales = daily_sales.reindex(idx, fill_value=0.0)
    daily_sales['date_day'] = daily_sales.index.date
    daily_sales = daily_sales.reset_index(drop=True)

    df = daily_sales.copy()
    df['date_day_dt'] = pd.to_datetime(df['date_day'])

    df['day_of_week'] = df['date_day_dt'].dt.dayofweek
    df['day_of_month'] = df['date_day_dt'].dt.day
    df['month'] = df['date_day_dt'].dt.month
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(float)
    df['is_payday'] = df['day_of_month'].isin([1, 15, 30, 31]).astype(float)
    df['is_retail_event'] = df['date_day_dt'].apply(check_retail_event)

    df['lag_1'] = df['net_sales'].shift(1)
    df['lag_2'] = df['net_sales'].shift(2)
    df['lag_7'] = df['net_sales'].shift(7)
    df['lag_14'] = df['net_sales'].shift(14)
    df['rolling_mean_7'] = df['net_sales'].shift(1).rolling(window=7, min_periods=1).mean()
    df['rolling_mean_14'] = df['net_sales'].shift(1).rolling(window=14, min_periods=1).mean()
    df['rolling_std_14'] = df['net_sales'].shift(1).rolling(window=14, min_periods=1).std().fillna(0.0)

    df['marketing_spend_7d'] = 0.0
    df['avg_discount_pct'] = 0.0
    df['stockout_rate'] = 0.0

    df_clean = df.dropna().reset_index(drop=True)
    if len(df_clean) < 7:
        return []

    test_size = min(7, len(df_clean) // 3)
    train_df = df_clean.iloc[:-test_size].reset_index(drop=True)
    test_df = df_clean.iloc[-test_size:].reset_index(drop=True)

    feature_cols = [
        'day_of_week', 'day_of_month', 'month', 'is_weekend', 'is_payday', 'is_retail_event',
        'lag_1', 'lag_2', 'lag_7', 'lag_14', 'rolling_mean_7', 'rolling_mean_14', 'rolling_std_14',
        'marketing_spend_7d', 'avg_discount_pct', 'stockout_rate'
    ]

    X_train = train_df[feature_cols]
    y_train = train_df['net_sales']
    X_test = test_df[feature_cols]
    y_test = test_df['net_sales']

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    test_predictions = np.clip(model.predict(X_test), 0, None)
    mae = float(np.mean(np.abs(y_test - test_predictions)))
    rmse = float(np.sqrt(np.mean((y_test - test_predictions) ** 2)))
    sum_actual = float(np.sum(y_test))
    wape = float(np.sum(np.abs(y_test - test_predictions)) / sum_actual * 100) if sum_actual > 0 else 0.0

    feature_impacts = {col: round(float(coef), 4) for col, coef in zip(feature_cols, model.coef_)}
    metrics_json = json.dumps({
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "wape": round(wape, 2),
        "channel": slice_channel,
        "category": slice_category,
        "evaluated_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "feature_impacts": feature_impacts
    })

    X_full = df_clean[feature_cols]
    y_full = df_clean['net_sales']
    full_model = Ridge(alpha=1.0)
    full_model.fit(X_full, y_full)

    forecast_dates = [df_clean['date_day'].max() + timedelta(days=i) for i in range(1, 8)]
    records = []
    history_p = df_clean.tail(14).copy().reset_index(drop=True)

    for f_date in forecast_dates:
        f_dt = pd.to_datetime(f_date)
        day_of_week = f_dt.dayofweek
        day_of_month = f_dt.day
        month = f_dt.month
        is_weekend = 1.0 if day_of_week in [5, 6] else 0.0
        is_payday = 1.0 if day_of_month in [1, 15, 30, 31] else 0.0
        is_retail_event = check_retail_event(f_dt)

        lag_1 = float(history_p.iloc[-1]['net_sales'])
        lag_2 = float(history_p.iloc[-2]['net_sales'])
        lag_7 = float(history_p.iloc[-7]['net_sales'])
        lag_14 = float(history_p.iloc[-14]['net_sales']) if len(history_p) >= 14 else lag_7
        rolling_mean_7 = float(history_p.tail(7)['net_sales'].mean())
        rolling_mean_14 = float(history_p.tail(14)['net_sales'].mean())
        rolling_std_14 = float(history_p.tail(14)['net_sales'].std()) if len(history_p) >= 14 else 0.0
        if np.isnan(rolling_std_14):
            rolling_std_14 = 0.0

        features = [[
            day_of_week, day_of_month, month, is_weekend, is_payday, is_retail_event,
            lag_1, lag_2, lag_7, lag_14, rolling_mean_7, rolling_mean_14, rolling_std_14,
            0.0, 0.0, 0.0
        ]]
        pred_sales = float(np.clip(full_model.predict(features)[0], 0, None))

        records.append({
            "date_day": f_date,
            "channel": slice_channel,
            "category": slice_category,
            "forecast_sales": round(pred_sales, 2),
            "model_name": f"Ridge Multi-Forecast ({slice_channel}/{slice_category})",
            "metrics_json": metrics_json,
            "created_at": datetime.utcnow()
        })

        new_row = pd.DataFrame([{
            'date_day': f_date,
            'net_sales': pred_sales
        }])
        history_p = pd.concat([history_p, new_row], ignore_index=True)

    return records

def run_sales_forecast():
    print("\n--- Running Multi-Channel & Multi-Category Sales Forecasting Engine ---")
    engine, db_type = get_db_connection()
    print(f"Connected to {db_type} database.")

    try:
        query = """
            SELECT t.transaction_timestamp as date_day, 
                   t.channel, 
                   p.category, 
                   (t.quantity * t.unit_price - t.discount) as net_sales
            FROM silver_transactions t
            LEFT JOIN silver_products p ON t.product_id = p.id
        """
        sales_df = pd.read_sql(query, con=engine)
        sales_df['date_day'] = pd.to_datetime(sales_df['date_day'], format='mixed', errors='coerce').dt.date
        sales_df['net_sales'] = sales_df['net_sales'].astype(float)
        sales_df['channel'] = sales_df['channel'].fillna("POS")
        sales_df['category'] = sales_df['category'].fillna("General")
    except Exception as e:
        print(f"Failed to read sales transactions with category join: {e}")
        return

    if sales_df.empty:
        print("Sales data is empty. Cannot forecast.")
        return

    all_records = []

    # 1. Total Aggregated Forecast (channel='ALL', category='ALL')
    total_records = train_and_forecast_slice(sales_df, "ALL", "ALL", engine)
    all_records.extend(total_records)

    # 2. Channel Slices
    channels = sales_df['channel'].unique()
    for ch in channels:
        ch_df = sales_df[sales_df['channel'] == ch]
        ch_records = train_and_forecast_slice(ch_df, ch, "ALL", engine)
        all_records.extend(ch_records)

    # 3. Category Slices
    categories = sales_df['category'].unique()
    for cat in categories:
        cat_df = sales_df[sales_df['category'] == cat]
        cat_records = train_and_forecast_slice(cat_df, "ALL", cat, engine)
        all_records.extend(cat_records)

    if not all_records:
        print("No forecast records generated.")
        return

    forecast_out_df = pd.DataFrame(all_records)
    print(f"Generated {len(forecast_out_df)} multi-forecast records across {len(channels)} channels and {len(categories)} categories.")

    # Save to PostgreSQL
    try:
        forecast_out_df['created_at'] = forecast_out_df['created_at'].dt.tz_localize(None)
        forecast_out_df['date_day'] = pd.to_datetime(forecast_out_df['date_day']).dt.tz_localize(None)
        forecast_out_df.to_sql("fact_sales_forecast", con=engine, if_exists="replace", index=False)
        print("Successfully saved multi-forecast to PostgreSQL.")
    except Exception as e:
        print(f"Could not save forecast to PostgreSQL: {e}")

    # Save to SQLite
    try:
        fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
        import sqlalchemy as sa
        sqlite_engine = sa.create_engine(f"sqlite:///{fallback_db}")
        forecast_out_df.to_sql("fact_sales_forecast", con=sqlite_engine, if_exists="replace", index=False)
        print("Successfully saved multi-forecast to SQLite.")
    except Exception as e:
        print(f"Could not save forecast to SQLite: {e}")

if __name__ == "__main__":
    run_sales_forecast()
