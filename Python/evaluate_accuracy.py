"""
驗證人流預測模型過去準確度之回測腳本 (Backtesting & Accuracy Evaluation)

驗證邏輯：
1. 從 MongoDB (或本機 CSV) 載入歷史數據與氣象特徵。
2. 進行時間序列交叉驗證 / 滾動式回測 (Walk-Forward / Time-Split Validation)：
   - 預設切分「最後 N 天（例如 7 天）」作為測試集 (Test Set)。
   - 之前的所有歷史資料作為訓練集 (Train Set)。
3. 使用與生產環境完全相同的 XGBoost 模型與特徵進行訓練與預測。
4. 計算各項指標並可輸出 JSON 結構或存入 MongoDB。
"""

import os
import sys
import json
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
import xgboost as xgb

# 匯入專案內的資料處理模組
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from Python.train_predict import (
    load_data,
    preprocess_data,
    sync_locations,
    fetch_weather_data,
    build_features,
    ALL_LOCATIONS
)

def evaluate_all(days_list=[7, 14, 30], tolerance_list=[3, 5, 10], save_to_db=False, output_json=False):
    if not output_json:
        print("=" * 70)
        print(f"🚀 開始回測驗證：評估天數 {days_list}")
        print("=" * 70)

    # 1. 載入資料 (只做一次，節省資源)
    df_raw, db = load_data()
    if df_raw.empty:
        if output_json:
            print(json.dumps({"error": "無法載入歷史數據"}))
        else:
            print("❌ 無法載入歷史數據，驗證中止。")
        return None

    coords = sync_locations(db)
    weather_data = fetch_weather_data(coords)
    df_clean = preprocess_data(df_raw)

    if not output_json:
        print("📊 建立特徵工程特徵...")
    df_features = build_features(df_clean, weather_data=weather_data)

    df_valid = df_features.dropna(subset=['peoNum', 'lag_last_week']).copy()
    if len(df_valid) < 500:
        df_valid = df_features.dropna(subset=['peoNum', 'lag_yesterday']).copy()

    max_time = df_valid['time'].max()
    all_results = {}

    for test_days in days_list:
        if not output_json:
            print("-" * 70)
            print(f"⏱️ 評估最近 {test_days} 天表現...")
            print("-" * 70)

        split_time = max_time - pd.Timedelta(days=test_days)
        train_df = df_valid[df_valid['time'] < split_time].copy()
        test_df = df_valid[df_valid['time'] >= split_time].copy()

        if test_df.empty or train_df.empty:
            if not output_json:
                print(f"⚠️ 針對 {test_days} 天的樣本不足，跳過。")
            continue

        train_encoded = pd.get_dummies(train_df, columns=['location'], drop_first=False)
        test_encoded = pd.get_dummies(test_df, columns=['location'], drop_first=False)

        location_cols = [f"location_{loc}" for loc in ALL_LOCATIONS]
        for col in location_cols:
            if col not in train_encoded.columns:
                train_encoded[col] = 0
            if col not in test_encoded.columns:
                test_encoded[col] = 0

        feature_cols = [
            'Time_sin', 'Time_cos', 'DayOfWeek_sin', 'DayOfWeek_cos', 'is_weekend', 'isHoliday', 'maxPeo',
            'lag_yesterday', 'lag_2days_ago', 'lag_last_week', 'lag_yesterday_trend',
            'max_temp', 'min_temp', 'avg_temp', 'precipitation_sum', 'precipitation_category'
        ] + location_cols

        X_train = train_encoded[feature_cols]
        y_train = train_encoded['peoNum']
        X_test = test_encoded[feature_cols]
        y_test = test_encoded['peoNum']

        model = xgb.XGBRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        preds = np.clip(preds, 0, test_df['maxPeo'].values)
        preds = np.round(preds)

        test_df['predicted'] = preds
        test_df['abs_error'] = np.abs(test_df['peoNum'] - test_df['predicted'])
        test_df['squared_error'] = (test_df['peoNum'] - test_df['predicted']) ** 2

        mae = float(round(test_df['abs_error'].mean(), 2))
        rmse = float(round(np.sqrt(test_df['squared_error'].mean()), 2))

        test_df['hour'] = test_df['time'].dt.hour
        active_df = test_df[(test_df['hour'] >= 6) & (test_df['hour'] <= 22)]
        active_mae = float(round(active_df['abs_error'].mean(), 2)) if not active_df.empty else mae
        active_rmse = float(round(np.sqrt(active_df['squared_error'].mean()), 2)) if not active_df.empty else rmse

        peak_df = test_df[(test_df['hour'] >= 17) & (test_df['hour'] <= 21)]
        peak_mae = float(round(peak_df['abs_error'].mean(), 2)) if not peak_df.empty else active_mae

        hit_rates = {}
        for tol in tolerance_list:
            rate = float(round((test_df['abs_error'] <= tol).mean() * 100, 1))
            active_rate = float(round((active_df['abs_error'] <= tol).mean() * 100, 1)) if not active_df.empty else rate
            hit_rates[f"within_{tol}"] = {
                "all": rate,
                "active": active_rate
            }

        locations_metrics = []
        for loc, grp in test_df.groupby('location'):
            loc_active = grp[(grp['hour'] >= 6) & (grp['hour'] <= 22)]
            l_mae = float(round(grp['abs_error'].mean(), 2))
            l_act_mae = float(round(loc_active['abs_error'].mean(), 2)) if not loc_active.empty else l_mae
            l_hit5 = float(round((loc_active['abs_error'] <= 5).mean() * 100, 1)) if not loc_active.empty else 0.0
            l_hit3 = float(round((loc_active['abs_error'] <= 3).mean() * 100, 1)) if not loc_active.empty else 0.0

            locations_metrics.append({
                'short': loc,
                'sampleCount': int(len(grp)),
                'allDayMae': l_mae,
                'activeHoursMae': l_act_mae,
                'hitRateWithin5': l_hit5,
                'hitRateWithin3': l_hit3
            })

        locations_metrics.sort(key=lambda x: x['activeHoursMae'])

        result = {
            'evaluatedAt': datetime.utcnow().isoformat(),
            'testDays': test_days,
            'timeRange': {
                'start': split_time.isoformat(),
                'end': max_time.isoformat()
            },
            'totalSamples': int(len(test_df)),
            'summary': {
                'overallMae': mae,
                'overallRmse': rmse,
                'activeHoursMae': active_mae,
                'activeHoursRmse': active_rmse,
                'peakHoursMae': peak_mae
            },
            'hitRates': hit_rates,
            'locations': locations_metrics
        }

        all_results[test_days] = result

        # 存入 MongoDB accuracy_evaluation collection
        if save_to_db and db is not None:
            try:
                db['accuracy_evaluation'].replace_one(
                    {'testDays': test_days},
                    result,
                    upsert=True
                )
                if not output_json:
                    print(f"💾 已將 {test_days} 天評估快照存入 MongoDB collection 'accuracy_evaluation'")
            except Exception as e:
                if not output_json:
                    print(f"⚠️ 儲存 {test_days} 天至 MongoDB 失敗: {e}")

        # 本地快照（支援 accuracy_evaluation_{days}.json 與預設 accuracy_evaluation.json）
        try:
            backup_file_days = os.path.join(os.path.dirname(__file__), f'accuracy_evaluation_{test_days}.json')
            with open(backup_file_days, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            if test_days == 7 or len(days_list) == 1:
                backup_default = os.path.join(os.path.dirname(__file__), 'accuracy_evaluation.json')
                with open(backup_default, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        if not output_json:
            print(f"🔹 {test_days} 天營業 MAE: ±{active_mae} 人 | ±5人命中率: {hit_rates['within_5']['active']}%")

    if output_json:
        print(json.dumps(all_results, ensure_ascii=False))
    elif not output_json:
        print("=" * 70)
        print("✅ 完成所有指定天數回測驗證！")
        print("=" * 70)

    return all_results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="評估過去人流預測準確度")
    parser.add_argument("--days", type=int, nargs="+", default=[7, 14, 30], help="回測驗證的天數清單 (預設: 7 14 30)")
    parser.add_argument("--save", action="store_true", help="將評估結果存入資料庫與快照")
    parser.add_argument("--json", action="store_true", help="以純 JSON 格式輸出")
    args = parser.parse_args()
    evaluate_all(days_list=args.days, save_to_db=args.save, output_json=args.json)

