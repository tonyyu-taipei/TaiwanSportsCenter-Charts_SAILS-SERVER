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

def evaluate(test_days=7, tolerance_list=[3, 5, 10], save_to_db=False, output_json=False):
    if not output_json:
        print("=" * 70)
        print(f"🚀 開始回測驗證：評估最近 {test_days} 天的人流預測準確度")
        print("=" * 70)

    # 1. 載入資料
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

    # 排除剛開始因 Lag 產生的缺失值
    df_valid = df_features.dropna(subset=['peoNum', 'lag_last_week']).copy()
    if len(df_valid) < 500:
        df_valid = df_features.dropna(subset=['peoNum', 'lag_yesterday']).copy()

    # 2. 時間切分 (Time-based Train/Test Split)
    max_time = df_valid['time'].max()
    split_time = max_time - pd.Timedelta(days=test_days)
    
    if not output_json:
        print(f"📅 資料集總時間區間: {df_valid['time'].min()} ~ {max_time}")
        print(f"✂️ 訓練集截止時間 : < {split_time}")
        print(f"🎯 測試集驗證時間 : >= {split_time} 至 {max_time} (共 {test_days} 天)")

    train_df = df_valid[df_valid['time'] < split_time].copy()
    test_df = df_valid[df_valid['time'] >= split_time].copy()

    if test_df.empty or train_df.empty:
        if output_json:
            print(json.dumps({"error": "訓練集或測試集樣本不足"}))
        else:
            print("❌ 訓練集或測試集樣本不足，請縮減 test_days 或檢查資料庫筆數。")
        return None

    # 3. One-hot encoding for locations
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

    # 4. 訓練模型
    if not output_json:
        print("🧠 正在訓練 XGBoost 回測模型...")
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

    # 5. 預測並評估
    preds = model.predict(X_test)
    preds = np.clip(preds, 0, test_df['maxPeo'].values)
    preds = np.round(preds)

    test_df['predicted'] = preds
    test_df['abs_error'] = np.abs(test_df['peoNum'] - test_df['predicted'])
    test_df['squared_error'] = (test_df['peoNum'] - test_df['predicted']) ** 2

    # 指標計算
    mae = float(round(test_df['abs_error'].mean(), 2))
    rmse = float(round(np.sqrt(test_df['squared_error'].mean()), 2))
    
    # 營業時段 (06:00 ~ 22:00) 專屬評估 (避免夜間 0 人的虛高命中)
    test_df['hour'] = test_df['time'].dt.hour
    active_df = test_df[(test_df['hour'] >= 6) & (test_df['hour'] <= 22)]
    active_mae = float(round(active_df['abs_error'].mean(), 2)) if not active_df.empty else mae
    active_rmse = float(round(np.sqrt(active_df['squared_error'].mean()), 2)) if not active_df.empty else rmse

    # 尖峰時段 (17:00 ~ 21:00)
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

    # 各場館分析
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

    # 封裝結果物件
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

    # 儲存快照至 MongoDB 或本機 JSON
    if save_to_db and db is not None:
        try:
            db['accuracy_evaluation'].replace_one(
                {'testDays': test_days},
                result,
                upsert=True
            )
            if not output_json:
                print("💾 已將評估快照存入 MongoDB collection 'accuracy_evaluation'")
        except Exception as e:
            if not output_json:
                print(f"⚠️ 儲存至 MongoDB 失敗: {e}")

    # 本機 backup
    backup_file = os.path.join(os.path.dirname(__file__), 'accuracy_evaluation.json')
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        if not output_json:
            print(f"💾 已將最新評估結果儲存至: {backup_file}")
    except Exception as e:
        pass

    if output_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("\n" + "=" * 70)
        print("📊 【總體回測評估成果】")
        print("=" * 70)
        print(f"🔹 全時段 MAE (平均絕對誤差)  : ±{mae} 人")
        print(f"🔹 全時段 RMSE (均方根誤差)   : {rmse} 人")
        print(f"🔹 營業時段 (06-22h) MAE      : ±{active_mae} 人 (RMSE: {active_rmse} 人)")
        print(f"🔹 晚間尖峰 (17-21h) MAE      : ±{peak_mae} 人")
        print("-" * 70)
        print("🎯 【命中率 (Hit Rate / 容許誤差範圍)】")
        for tol in tolerance_list:
            hr = hit_rates[f"within_{tol}"]
            print(f"   誤差在 ±{tol:2d} 人以內: 全時段 {hr['all']:5.1f}% | 營業時段 {hr['active']:5.1f}%")
        print("=" * 70)

    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="評估過去人流預測準確度")
    parser.add_argument("--days", type=int, default=7, help="回測驗證的天數 (預設: 7 天)")
    parser.add_argument("--save", action="store_true", help="將評估結果存入資料庫與快照")
    parser.add_argument("--json", action="store_true", help="以純 JSON 格式輸出")
    args = parser.parse_args()
    evaluate(test_days=args.days, save_to_db=args.save, output_json=args.json)
